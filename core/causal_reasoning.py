"""
Causal Reasoning Engine for EconStats.

This module provides causal explanations for economic relationships.
Instead of just "inflation is falling", it explains WHY inflation is falling.

The Problem:
    Current analysis says WHAT is happening but not WHY. An economist always
    explains the causal mechanism. When we say "unemployment rose," we should
    explain that Fed rate hikes work with a lag and are now filtering through
    to the labor market.

The Solution:
    This module encodes the causal chains that economists understand:
    - What causes what
    - Through which mechanism
    - With what typical lag
    - And what should we expect next

It also enforces epistemic humility - we hedge causal claims appropriately
because in economics, causation is hard to establish with certainty.

Key Principles:
    1. Every economic relationship has a REASON - explain it
    2. Transmission mechanisms matter - HOW does A cause B?
    3. Lags are critical - WHEN does the effect show up?
    4. Economic causation is HARD to establish - use hedged language
    5. Multiple factors usually contribute to any outcome

Usage:
    from core.causal_reasoning import (
        # Causal chain system
        CAUSAL_CHAINS,
        detect_causal_patterns,
        explain_relationship,
        get_forward_implications,
        build_causal_narrative,
        # Hedging utilities
        hedge_causal_claim,
        get_hedging_phrase,
        transform_overconfident_language,
    )

    # Detect what's happening and why
    patterns = detect_causal_patterns(data_context)

    # Explain a specific relationship
    explanation = explain_relationship('UNRATE', 'CPIAUCSL', data)

    # Get forward-looking implications
    implications = get_forward_implications(data_context, patterns)

    # Build a full narrative
    narrative = build_causal_narrative(query, data_context, series_data)
"""

import random
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum


# =============================================================================
# CAUSAL CHAIN DATA STRUCTURES
# =============================================================================

class CausalStrength(Enum):
    """How reliably does the cause lead to the effect?"""
    STRONG = "strong"           # Works most of the time (>80% historical accuracy)
    MODERATE = "moderate"       # Works often but with exceptions (50-80%)
    CONDITIONAL = "conditional" # Works under certain conditions


@dataclass
class CausalChain:
    """
    A single causal relationship in the economy.

    Attributes:
        id: Unique identifier for this chain
        cause: What starts the chain (e.g., "Fed rate hikes")
        mechanism: HOW the cause leads to the effect - the transmission channel
        effect: The resulting outcome
        lag: Typical time delay (human-readable)
        lag_months: Lag range in months (min, max) for quantitative analysis
        strength: How reliable is this relationship
        relevant_series: FRED series to monitor for this chain
        conditions: Under what conditions does this chain activate
        counterexamples: When has this chain failed historically
        key_insight: The most important thing to understand
    """
    id: str
    cause: str
    mechanism: str
    effect: str
    lag: str
    lag_months: Tuple[int, int] = (0, 0)
    strength: CausalStrength = CausalStrength.MODERATE
    relevant_series: List[str] = field(default_factory=list)
    conditions: str = ""
    counterexamples: str = ""
    key_insight: str = ""


# =============================================================================
# MASTER CAUSAL CHAINS DICTIONARY
# Each chain explains WHY something happens, not just THAT it happened
# =============================================================================

CAUSAL_CHAINS: Dict[str, CausalChain] = {

    # =========================================================================
    # FED POLICY TRANSMISSION
    # How the Fed's actions ripple through the economy
    # =========================================================================

    'fed_hikes_inflation': CausalChain(
        id='fed_hikes_inflation',
        cause='Fed rate hikes',
        mechanism=(
            'Higher rates increase borrowing costs across the economy. Mortgages, car loans, '
            'and credit cards all get more expensive. This reduces demand for housing, autos, '
            'and discretionary spending. With less demand, businesses lose pricing power and '
            'slow their price increases.'
        ),
        effect='Inflation cools as demand weakens',
        lag='12-18 months',
        lag_months=(12, 18),
        strength=CausalStrength.STRONG,
        relevant_series=['FEDFUNDS', 'CPIAUCSL', 'PCEPILFE', 'MORTGAGE30US'],
        conditions='Most effective when inflation is demand-driven, not supply-driven',
        counterexamples='1970s: Fed raised rates but inflation persisted due to supply shocks (oil)',
        key_insight=(
            'Rate hikes work slowly because they cool demand, which cools prices - but prices are '
            'sticky. Businesses resist lowering prices until they see sustained weaker demand.'
        ),
    ),

    'fed_hikes_unemployment': CausalChain(
        id='fed_hikes_unemployment',
        cause='Restrictive monetary policy',
        mechanism=(
            'Higher borrowing costs reduce business investment and consumer spending. Companies '
            'first cut hours, then freeze hiring, then lay off workers. The sequence is: slower '
            'demand -> excess inventory -> production cuts -> layoffs.'
        ),
        effect='Unemployment rises',
        lag='18-24 months',
        lag_months=(18, 24),
        strength=CausalStrength.STRONG,
        relevant_series=['FEDFUNDS', 'UNRATE', 'PAYEMS', 'ICSA'],
        conditions='Depends on how much the Fed tightens relative to neutral rate',
        counterexamples='2023: Fed hiked aggressively but labor market stayed strong due to labor hoarding',
        key_insight=(
            'Unemployment is the LAST thing to respond to Fed policy. By the time unemployment '
            'rises meaningfully, the economy has already been slowing for 12+ months.'
        ),
    ),

    'fed_hikes_housing': CausalChain(
        id='fed_hikes_housing',
        cause='Fed rate increases',
        mechanism=(
            'The Fed raises short-term rates -> Treasury yields rise -> Mortgage rates follow '
            '(typically 2-3% above 10Y Treasury). Higher mortgage rates mean higher monthly '
            'payments, pricing out buyers. A rate jump from 3% to 7% can add $1,000/month to a '
            'typical mortgage, pushing many buyers to the sidelines.'
        ),
        effect='Housing activity slows; eventually prices moderate',
        lag='Mortgage rates: immediate. Sales: 2-6 months. Prices: 6-18 months.',
        lag_months=(6, 18),
        strength=CausalStrength.STRONG,
        relevant_series=['MORTGAGE30US', 'EXHOSLUSM495S', 'CSUSHPINSA', 'HOUST'],
        conditions='Most powerful when housing is stretched (high prices relative to income)',
        key_insight=(
            'Housing is the most interest-rate-sensitive sector. It often leads the economy '
            'into and out of recessions because mortgages are long-term, rate-sensitive loans.'
        ),
    ),

    'fed_hikes_dollar': CausalChain(
        id='fed_hikes_dollar',
        cause='Fed rate hikes (relative to other central banks)',
        mechanism=(
            'Higher US rates attract foreign capital seeking better returns. Foreign investors '
            'need dollars to buy US Treasuries, so they sell their currencies and buy dollars. '
            'This increases demand for dollars and strengthens the exchange rate.'
        ),
        effect='Dollar strengthens against other currencies',
        lag='Immediate to 3 months',
        lag_months=(0, 3),
        strength=CausalStrength.MODERATE,
        relevant_series=['FEDFUNDS', 'DTWEXBGS', 'DGS10', 'DGS2'],
        conditions='Works when US raises rates faster than Europe/Japan/others',
        counterexamples='If markets expect US rates to fall soon, dollar may weaken despite current high rates',
        key_insight=(
            'Exchange rates are about RELATIVE interest rates. The Fed raising rates alone does '
            'not guarantee a stronger dollar - it depends on what other central banks do.'
        ),
    ),

    'fed_cuts_stimulus': CausalChain(
        id='fed_cuts_stimulus',
        cause='Fed rate cuts',
        mechanism=(
            'Lower rates reduce borrowing costs. Mortgage rates fall, making homes more affordable. '
            'Car loans get cheaper. Businesses can finance expansion at lower cost. This encourages '
            'spending and investment. Asset prices (stocks, homes) typically rise as lower rates '
            'increase the present value of future cash flows.'
        ),
        effect='Economic activity accelerates; asset prices rise',
        lag='6-12 months for real economy; stock market often responds immediately',
        lag_months=(6, 12),
        strength=CausalStrength.MODERATE,
        relevant_series=['FEDFUNDS', 'SP500', 'GDPC1', 'MORTGAGE30US'],
        conditions='Works best when banks are willing to lend and consumers/businesses want to borrow',
        counterexamples='2008-2009: Zero rates did not immediately revive economy due to broken banking system',
        key_insight=(
            'You can lead a horse to water but cannot make it drink. Low rates only stimulate if '
            'people want to borrow. In severe recessions, fear dominates even with zero rates.'
        ),
    ),

    # =========================================================================
    # LABOR MARKET DYNAMICS
    # How the job market works and what signals to watch
    # =========================================================================

    'tight_labor_wages': CausalChain(
        id='tight_labor_wages',
        cause='Low unemployment / tight labor market',
        mechanism=(
            'When unemployment is low, workers have options. They can quit for better jobs, and '
            'employers struggle to fill positions. This gives workers bargaining power. Employers '
            'must raise wages to attract and retain talent. The ratio of job openings to unemployed '
            'workers captures this - when it exceeds 1.5, wage pressure intensifies.'
        ),
        effect='Wage growth accelerates',
        lag='0-6 months',
        lag_months=(0, 6),
        strength=CausalStrength.STRONG,
        relevant_series=['UNRATE', 'CES0500000003', 'ECIWAG', 'JTSJOL'],
        conditions='Most pronounced when unemployment is below 4% (below NAIRU)',
        key_insight=(
            'The Phillips Curve lives: low unemployment still leads to wage pressure. But the '
            'relationship has flattened - you need very low unemployment to see big wage gains.'
        ),
    ),

    'quits_rate_signal': CausalChain(
        id='quits_rate_signal',
        cause='High quits rate',
        mechanism=(
            'Workers only quit voluntarily when confident they can find better jobs elsewhere. '
            'A high quits rate (above 2.5%) signals a tight labor market where workers have the '
            'upper hand. Conversely, when quits drop sharply, it often means workers are scared '
            'about the economy and hanging onto their current jobs.'
        ),
        effect='Signals tight labor conditions and worker confidence',
        lag='Contemporaneous (real-time signal)',
        lag_months=(0, 0),
        strength=CausalStrength.STRONG,
        relevant_series=['JTSQUR', 'UNRATE', 'JTSJOL'],
        conditions='Quits rate below 2% often precedes recession',
        key_insight=(
            'The quits rate is the clearest window into worker confidence. When people stop '
            'quitting, they are worried - even if unemployment has not risen yet.'
        ),
    ),

    'openings_hiring_disconnect': CausalChain(
        id='openings_hiring_disconnect',
        cause='Falling job openings with steady hiring',
        mechanism=(
            'When job openings fall but hiring stays stable, the labor market is normalizing '
            'rather than collapsing. Companies are pulling back their aggressive recruiting '
            '(fewer postings) but still filling positions as needed. This is a soft landing '
            'signal - cooling without crashing.'
        ),
        effect='Labor market rebalancing (soft landing signal)',
        lag='Contemporaneous',
        lag_months=(0, 0),
        strength=CausalStrength.MODERATE,
        relevant_series=['JTSJOL', 'JTSHIR', 'PAYEMS'],
        conditions='Only applies when hiring holds up; if hiring also falls, signals trouble',
        key_insight=(
            'Job openings per unemployed person falling from 2.0 to 1.2 is healthy normalization. '
            'Falling below 1.0 historically signals recession risk.'
        ),
    ),

    'claims_spike_warning': CausalChain(
        id='claims_spike_warning',
        cause='Sharp rise in initial unemployment claims',
        mechanism=(
            'Initial claims measure NEW layoffs each week. When claims spike above 300K (or rise '
            '50%+ from recent lows), it signals businesses are actively cutting staff. This is a '
            'leading indicator because layoffs precede rising unemployment - it takes time for '
            'laid-off workers to show up in unemployment statistics.'
        ),
        effect='Unemployment will rise within 1-3 months',
        lag='1-3 months lead time on unemployment',
        lag_months=(1, 3),
        strength=CausalStrength.STRONG,
        relevant_series=['ICSA', 'UNRATE', 'PAYEMS'],
        conditions='Sustained rise (4+ weeks) is more reliable than one-week spike',
        key_insight=(
            'Watch the 4-week moving average of claims. A spike to 250K is noise; sustained '
            'move above 300K is a warning. Above 400K typically means recession has begun.'
        ),
    ),

    'prime_age_employment': CausalChain(
        id='prime_age_employment',
        cause='Prime-age (25-54) employment-population ratio changes',
        mechanism=(
            'The prime-age EPOP is the cleanest measure of labor market health. Unlike the '
            'unemployment rate, it is not affected by people leaving the labor force. When '
            'prime-age EPOP is above 80%, the labor market is strong. Below 78% signals slack.'
        ),
        effect='Indicates true labor market strength/weakness',
        lag='Contemporaneous',
        lag_months=(0, 0),
        strength=CausalStrength.STRONG,
        relevant_series=['LNS12300060', 'UNRATE', 'CIVPART'],
        key_insight=(
            'The unemployment rate can fall for bad reasons (people giving up looking). '
            'Prime-age EPOP only rises when people are actually working.'
        ),
    ),

    # =========================================================================
    # INFLATION DYNAMICS
    # How inflation works and why it is so sticky
    # =========================================================================

    'shelter_lag': CausalChain(
        id='shelter_lag',
        cause='Market rent changes',
        mechanism=(
            'The official CPI shelter measure lags market rents by 12-18 months. Why? The BLS '
            'measures what renters are ACTUALLY paying, not asking rents. Most renters are locked '
            'into year-long leases signed months ago. So when Zillow shows rents falling, CPI '
            'shelter keeps rising for another year as expensive old leases roll off slowly.'
        ),
        effect='CPI shelter inflation lags market rents by 12+ months',
        lag='12-18 months',
        lag_months=(12, 18),
        strength=CausalStrength.STRONG,
        relevant_series=['CUSR0000SAH1', 'CUSR0000SEHA', 'zillow_zori_national'],
        conditions='The lag is mechanical - it always happens',
        key_insight=(
            'This is the SINGLE MOST IMPORTANT thing to understand about 2023-2026 inflation. '
            'Shelter is 1/3 of CPI. The official number was baked in 12-18 months ago.'
        ),
    ),

    'goods_services_split': CausalChain(
        id='goods_services_split',
        cause='Supply chain normalization / demand shift',
        mechanism=(
            'Goods inflation (cars, electronics, clothing) is driven by global supply chains. '
            'When supply chains heal, goods prices fall or go flat. Services inflation (haircuts, '
            'doctors, restaurants) is driven by local labor costs. Services stay elevated as long '
            'as wage growth is high.'
        ),
        effect='Goods deflation while services stay sticky',
        lag='Goods: immediate to supply changes. Services: 6-12 month lag to wages.',
        lag_months=(0, 12),
        strength=CausalStrength.STRONG,
        relevant_series=['CUSR0000SAC', 'CUSR0000SAS', 'CPIAUCSL'],
        key_insight=(
            'The last mile of disinflation is hard because it is all about services (60% of '
            'consumption). Goods can outright deflate, but services almost never do.'
        ),
    ),

    'wage_price_spiral': CausalChain(
        id='wage_price_spiral',
        cause='Persistent high inflation eroding real wages',
        mechanism=(
            'When inflation is high for long, workers demand raises to keep up. Businesses pass '
            'higher labor costs to consumers. This creates a self-reinforcing cycle. BUT - and '
            'this is crucial - spirals only happen when EXPECTATIONS become unanchored. If workers '
            'believe inflation is temporary, they accept one-time catch-up raises. If they think '
            'inflation is permanent, they keep demanding more.'
        ),
        effect='Self-reinforcing inflation cycle (if expectations unanchor)',
        lag='Ongoing - takes 2-3 years to develop',
        lag_months=(24, 36),
        strength=CausalStrength.CONDITIONAL,
        relevant_series=['CES0500000003', 'CPIAUCSL', 'T5YIFR', 'MICH'],
        conditions='Only occurs when long-term inflation expectations rise above 3%',
        counterexamples='2021-2023: 9% inflation but no spiral because expectations stayed anchored',
        key_insight=(
            'Spirals are about EXPECTATIONS, not actual inflation. The Fed spends so much time '
            'on communication because maintaining expectations IS the job.'
        ),
    ),

    'energy_pass_through': CausalChain(
        id='energy_pass_through',
        cause='Oil/energy price spike',
        mechanism=(
            'Energy costs affect everything - transportation, manufacturing, heating. When oil '
            'spikes, it first shows up in headline CPI through gasoline. Then it filters into '
            'transportation costs, then into goods prices as shipping costs rise. The pass-through '
            'to core inflation is typically 0.1-0.2% for each 10% oil price increase.'
        ),
        effect='Headline inflation spikes immediately; core follows with lag',
        lag='Headline: immediate. Core: 3-6 months. Full pass-through: 6-12 months.',
        lag_months=(3, 12),
        strength=CausalStrength.STRONG,
        relevant_series=['DCOILWTICO', 'CPIAUCSL', 'CPILFESL', 'CPIENGSL'],
        conditions='Pass-through is larger when starting from high capacity utilization',
        key_insight=(
            'This is why the Fed looks through oil shocks - they spike headline inflation '
            'temporarily but rarely affect long-run trend. Unless they trigger a wage spiral.'
        ),
    ),

    'inflation_expectations_anchor': CausalChain(
        id='inflation_expectations_anchor',
        cause='Long-term inflation expectations (5Y5Y forward)',
        mechanism=(
            'If people believe inflation will return to 2%, they behave accordingly - accepting '
            'moderate wage increases, not front-running price hikes. This becomes self-fulfilling. '
            'The 5-year-5-year forward rate measures what markets expect inflation to average '
            '5-10 years from now. As long as this stays near 2%, temporary inflation shocks '
            'remain temporary.'
        ),
        effect='Actual inflation tends toward expectations over time',
        lag='Expectations are forward-looking; they affect behavior immediately',
        lag_months=(0, 0),
        strength=CausalStrength.STRONG,
        relevant_series=['T5YIFR', 'MICH', 'EXPINF1YR'],
        key_insight=(
            'The Fed has spent 40 years building credibility. That credibility - the belief '
            'that the Fed will do whatever it takes - is what keeps expectations anchored.'
        ),
    ),

    'supercore_signal': CausalChain(
        id='supercore_signal',
        cause='Core services ex-housing inflation',
        mechanism=(
            'The Fed watches supercore (services minus shelter and energy) because it strips '
            'out the lagged shelter measure and volatile energy. What is left is mostly '
            'labor-intensive services: healthcare, education, dining, travel. Supercore tracks '
            'wage growth closely and shows the underlying demand-driven inflation trend.'
        ),
        effect='Best signal of underlying inflation pressure',
        lag='Real-time reflection of labor market tightness',
        lag_months=(0, 0),
        strength=CausalStrength.MODERATE,
        relevant_series=['CUSR0000SASLE', 'PCEPILFE', 'CES0500000003'],
        key_insight=(
            'If supercore is falling while headline shelter is high, the Fed knows disinflation '
            'is real. The shelter number will catch up. This gave them confidence in 2023-2024.'
        ),
    ),

    # =========================================================================
    # RECESSION SIGNALS
    # What warns us before a recession hits
    # =========================================================================

    'yield_curve_recession': CausalChain(
        id='yield_curve_recession',
        cause='Inverted yield curve (2Y > 10Y)',
        mechanism=(
            'Normally, long-term bonds pay more than short-term (compensation for locking up '
            'money). An inversion means investors expect the Fed to cut rates in the future - '
            'usually because they expect a recession. Short rates stay high (current Fed policy), '
            'but long rates fall (expected future cuts). The signal works because bond markets '
            'are forward-looking and have money on the line.'
        ),
        effect='Recession typically follows in 12-18 months',
        lag='12-18 months average lead time',
        lag_months=(12, 18),
        strength=CausalStrength.STRONG,
        relevant_series=['T10Y2Y', 'T10Y3M', 'DGS2', 'DGS10'],
        conditions='Works best when inversion is deep (> 50bp) and sustained (> 3 months)',
        counterexamples='About 15% of inversions did not lead to recession (e.g., 1998)',
        key_insight=(
            'The curve has predicted every recession since 1970. Not foolproof (some false '
            'positives), but when it inverts deeply for months, pay attention.'
        ),
    ),

    'sahm_rule_mechanics': CausalChain(
        id='sahm_rule_mechanics',
        cause='3-month unemployment avg rises 0.5pp above 12-month low',
        mechanism=(
            'Claudia Sahm observed that unemployment rises slowly at first, then accelerates into '
            'recession. The 0.5 percentage point threshold catches this inflection - the moment '
            'when a cooling labor market becomes a collapsing one. Once unemployment starts '
            'rising this fast, it typically keeps rising (momentum builds as layoffs cause less '
            'spending, causing more layoffs).'
        ),
        effect='Has correctly signaled every recession since 1970',
        lag='Real-time signal (no lead time - signals recession has begun)',
        lag_months=(0, 0),
        strength=CausalStrength.STRONG,
        relevant_series=['SAHMREALTIME', 'UNRATE'],
        conditions='Works in real-time; by the time it triggers, recession may already be underway',
        key_insight=(
            'The Sahm Rule is not a forecast - it is a recession CONFIRMATION. If it triggers '
            'and you are wondering if we are in a recession, the answer is almost certainly yes.'
        ),
    ),

    'leading_indicators_composite': CausalChain(
        id='leading_indicators_composite',
        cause='Conference Board Leading Economic Index (LEI) decline',
        mechanism=(
            'The LEI combines 10 leading indicators: jobless claims, building permits, stock '
            'prices, credit conditions, and more. When multiple leading indicators deteriorate '
            'together, it signals broad-based weakness. A sustained decline (6+ months) at more '
            'than 4% annualized has preceded every recession.'
        ),
        effect='Signals recession 6-12 months ahead',
        lag='6-12 months',
        lag_months=(6, 12),
        strength=CausalStrength.MODERATE,
        relevant_series=['ICSA', 'PERMIT', 'SP500', 'UMCSENT'],
        conditions='More reliable when decline is broad (many components falling) vs narrow',
        counterexamples='2022-2023: LEI fell for 24 months but no recession (false alarm)',
        key_insight=(
            'The LEI gave a false alarm in 2022-2023 because manufacturing indicators tanked '
            'while services and labor stayed strong. Watch for broad-based weakness, not just one sector.'
        ),
    ),

    'credit_spread_warning': CausalChain(
        id='credit_spread_warning',
        cause='Corporate credit spreads widening sharply',
        mechanism=(
            'Credit spreads measure the extra yield investors demand to hold corporate bonds vs '
            'Treasuries. When spreads widen, investors are getting nervous about companies '
            'ability to repay debt. This tightens financial conditions, raises borrowing costs '
            'for businesses, and can become self-fulfilling if companies cannot roll over debt.'
        ),
        effect='Signals financial stress and potential credit crunch',
        lag='Often leads economic weakness by 3-6 months',
        lag_months=(3, 6),
        strength=CausalStrength.MODERATE,
        relevant_series=['BAA10Y', 'BAMLH0A0HYM2', 'NFCI'],
        conditions='Most concerning when combined with bank lending standards tightening',
        key_insight=(
            'Credit spreads spiking while unemployment is still low is an early warning. '
            'It means financial markets see trouble before the labor market shows it.'
        ),
    ),

    # =========================================================================
    # CONSUMER BEHAVIOR
    # What drives spending and how it affects the economy
    # =========================================================================

    'sentiment_spending': CausalChain(
        id='sentiment_spending',
        cause='Low consumer sentiment',
        mechanism=(
            'When consumers feel worried about the economy (job security, inflation, political '
            'uncertainty), they pull back on discretionary spending. They delay big purchases, '
            'save more, and cut back on dining out and travel. Consumer spending is 70% of GDP, '
            'so sentiment shifts can have real effects on growth.'
        ),
        effect='Consumption growth slows',
        lag='1-3 months',
        lag_months=(1, 3),
        strength=CausalStrength.MODERATE,
        relevant_series=['UMCSENT', 'PCE', 'RSXFS'],
        conditions='Relationship is stronger during recessions than expansions',
        counterexamples='2022: Sentiment crashed to record lows but spending stayed strong (excess savings)',
        key_insight=(
            'Sentiment is a better predictor of DIRECTION than MAGNITUDE. Falling sentiment '
            'means slower growth, but how much slower depends on income, wealth, and credit.'
        ),
    ),

    'excess_savings_buffer': CausalChain(
        id='excess_savings_buffer',
        cause='Accumulated excess savings (post-stimulus)',
        mechanism=(
            'When households have excess savings (above their normal savings rate), they continue '
            'spending even when sentiment is low or income growth slows. The savings act as a '
            'buffer, delaying the normal relationship between sentiment and spending. Only when '
            'excess savings are depleted do normal dynamics reassert.'
        ),
        effect='Spending resilience despite negative signals',
        lag='Until savings depleted (varies, typically 12-24 months)',
        lag_months=(12, 24),
        strength=CausalStrength.MODERATE,
        relevant_series=['PSAVERT', 'PCE', 'UMCSENT'],
        conditions='Relevant after fiscal stimulus or periods of forced savings (lockdowns)',
        key_insight=(
            'This explains 2022-2023: sentiment crashed but spending held up because households '
            'were drawing down $2T in pandemic savings. Once depleted, normal dynamics return.'
        ),
    ),

    'wealth_effect_spending': CausalChain(
        id='wealth_effect_spending',
        cause='Stock market or home price changes',
        mechanism=(
            'When people see their 401(k) or home value rise, they feel wealthier and spend more '
            '(even if they do not sell). Rule of thumb: each $1 gain in stock wealth leads to '
            '2-4 cents more annual spending; $1 in housing wealth leads to 5-8 cents more (because '
            'housing feels more permanent and can be borrowed against).'
        ),
        effect='Consumer spending moves with asset prices',
        lag='1-6 months',
        lag_months=(1, 6),
        strength=CausalStrength.MODERATE,
        relevant_series=['SP500', 'CSUSHPINSA', 'PCE'],
        conditions='Effect is stronger for older, wealthier households',
        key_insight=(
            'The Fed knows this - one reason they care about stock prices is the wealth effect. '
            'A 20% stock crash reduces spending meaningfully within a few quarters.'
        ),
    ),

    'credit_card_stress': CausalChain(
        id='credit_card_stress',
        cause='Rising credit card delinquencies',
        mechanism=(
            'Credit card delinquencies (30+ days late) rising signals consumers are stretching. '
            'First comes increased borrowing, then missed payments, then defaults. Rising '
            'delinquencies, especially among subprime borrowers, often precede broader consumer '
            'stress. Banks respond by tightening credit, which further reduces spending capacity.'
        ),
        effect='Signals consumer distress; may precede spending pullback',
        lag='Consumer spending usually weakens 3-6 months after delinquencies rise',
        lag_months=(3, 6),
        strength=CausalStrength.MODERATE,
        relevant_series=['DRCCLACBS', 'TOTALSL', 'PCE'],
        conditions='More concerning when combined with rising unemployment',
        key_insight=(
            'Credit card delinquencies rising while unemployment is low means households are '
            'stretched even with jobs. That is a vulnerability - they have no cushion if layoffs come.'
        ),
    ),

    # =========================================================================
    # INTERNATIONAL LINKAGES
    # How the global economy affects the US
    # =========================================================================

    'dollar_trade_impact': CausalChain(
        id='dollar_trade_impact',
        cause='Strong dollar',
        mechanism=(
            'A strong dollar makes US exports more expensive for foreign buyers and imports '
            'cheaper for US consumers. This hurts US manufacturers (lose competitiveness) but '
            'helps consumers (cheaper imports). For multinationals, a strong dollar reduces '
            'the value of foreign earnings when translated back to dollars.'
        ),
        effect='Trade deficit widens; manufacturing slows; import prices fall',
        lag='3-6 months for trade flows; immediate for corporate earnings',
        lag_months=(3, 6),
        strength=CausalStrength.MODERATE,
        relevant_series=['DTWEXBGS', 'BOPGSTB', 'MANEMP'],
        key_insight=(
            'A strong dollar is disinflationary for the US (cheaper imports) but contractionary '
            'for US manufacturing. It exports our inflation to other countries.'
        ),
    ),

    'china_goods_deflation': CausalChain(
        id='china_goods_deflation',
        cause='Weak Chinese demand / excess capacity',
        mechanism=(
            'When China has excess industrial capacity (factories built for domestic demand that '
            'did not materialize), they export at low prices. These cheap goods put downward '
            'pressure on US goods prices, especially electronics, appliances, and equipment.'
        ),
        effect='US goods deflation; helps overall inflation but hurts US manufacturers',
        lag='3-6 months as goods move through supply chains',
        lag_months=(3, 6),
        strength=CausalStrength.MODERATE,
        relevant_series=['CUSR0000SAC', 'IMPGSC1'],
        conditions='Most pronounced when China is in economic slump (property crisis)',
        key_insight=(
            'China exporting deflation helped the Fed in 2023-2024. US goods prices fell partly '
            'because Chinese factories were desperate for orders.'
        ),
    ),

    'global_rate_divergence': CausalChain(
        id='global_rate_divergence',
        cause='Fed policy diverging from other central banks',
        mechanism=(
            'When the Fed raises rates while ECB/BOJ hold steady, capital flows to the US seeking '
            'higher returns. This strengthens the dollar, which tightens financial conditions for '
            'emerging markets (many have dollar-denominated debt). It also reduces imported '
            'inflation for the US while exporting it to trade partners.'
        ),
        effect='Dollar strength; EM stress; US imports deflation',
        lag='Immediate for exchange rates; 3-6 months for trade effects',
        lag_months=(0, 6),
        strength=CausalStrength.MODERATE,
        relevant_series=['FEDFUNDS', 'DTWEXBGS', 'T5YIFR'],
        key_insight=(
            'Monetary policy is partially a zero-sum game globally. When the US tightens more '
            'than others, it effectively exports some inflation to trading partners.'
        ),
    ),

    'oil_shock_transmission': CausalChain(
        id='oil_shock_transmission',
        cause='Global oil supply disruption',
        mechanism=(
            'Oil shocks affect the US economy through multiple channels: direct energy costs '
            '(gasoline, heating), transportation costs (shipping), petrochemical inputs (plastics, '
            'fertilizer). Unlike the 1970s, the US is now a net oil exporter, so high oil prices '
            'benefit the energy sector while hurting consumers. The net effect is smaller.'
        ),
        effect='Inflation spike; mixed GDP impact (helps oil states, hurts consumers)',
        lag='Gasoline prices: immediate. Broader effects: 3-6 months.',
        lag_months=(0, 6),
        strength=CausalStrength.MODERATE,
        relevant_series=['DCOILWTICO', 'CPIENGSL', 'CPIAUCSL'],
        conditions='Impact greater when starting from high capacity utilization',
        key_insight=(
            'The US is much less oil-sensitive than in the 1970s. We produce more domestically, '
            'cars are more efficient, and the economy is more services-based.'
        ),
    ),

    # =========================================================================
    # FINANCIAL MARKET SIGNALS
    # What markets tell us about the economy
    # =========================================================================

    'stock_market_leading': CausalChain(
        id='stock_market_leading',
        cause='Stock market declines',
        mechanism=(
            'Stock prices are forward-looking - they reflect expectations about future earnings. '
            'A sustained 20%+ decline often (but not always) signals that markets see economic '
            'weakness ahead. The mechanism works both ways: falling stocks reduce wealth, which '
            'reduces spending, which can cause the weakness investors feared.'
        ),
        effect='Often precedes economic weakness by 3-9 months',
        lag='3-9 months',
        lag_months=(3, 9),
        strength=CausalStrength.MODERATE,
        relevant_series=['SP500', 'GDPC1', 'PCE'],
        conditions='More reliable when decline is broad-based (not just tech)',
        counterexamples='2022 bear market: stocks fell 25% but no recession followed',
        key_insight=(
            'As Samuelson quipped: The stock market has predicted 9 of the last 5 recessions. '
            'Stocks often overreact. A crash warrants attention but is not a guarantee.'
        ),
    ),

    'vix_stress_signal': CausalChain(
        id='vix_stress_signal',
        cause='VIX (volatility index) spike',
        mechanism=(
            'The VIX measures expected stock market volatility. A spike above 30 signals fear '
            'and uncertainty. While not directly causal, high VIX often accompanies credit '
            'tightening, reduced risk-taking, and risk-off behavior. Sustained high VIX (>25 '
            'for months) can become self-fulfilling as businesses delay investment.'
        ),
        effect='Signals financial stress; may tighten financial conditions',
        lag='Contemporaneous signal; effects unfold over 1-3 months',
        lag_months=(0, 3),
        strength=CausalStrength.MODERATE,
        relevant_series=['VIXCLS', 'NFCI', 'BAA10Y'],
        key_insight=(
            'VIX spikes are usually temporary (days to weeks). Sustained elevation is concerning. '
            'A VIX above 35 for a month usually means something is genuinely broken.'
        ),
    ),
}


# =============================================================================
# HEDGING PHRASES BY CONFIDENCE LEVEL
# =============================================================================

HEDGING_PHRASES: Dict[str, List[str]] = {
    # High confidence: Strong historical/theoretical support, data clearly aligns
    # Use when: Multiple independent data sources point same direction,
    # well-established economic relationships
    'high_confidence': [
        "is consistent with",
        "aligns with historical patterns of",
        "follows the typical pattern of",
        "is in line with what economic theory predicts from",
        "matches the expected response to",
        "corresponds to",
    ],

    # Medium confidence: Reasonable interpretation, some uncertainty
    # Use when: Single data series, plausible causal mechanism,
    # but alternative explanations exist
    'medium_confidence': [
        "may reflect",
        "could be influenced by",
        "one factor may be",
        "likely related to",
        "appears to be associated with",
        "seems to follow from",
        "might be responding to",
        "could be attributed to",
        "is potentially linked to",
    ],

    # Low confidence: Speculative but worth noting
    # Use when: Limited data, complex/unclear mechanisms,
    # or novel situations without historical precedent
    'low_confidence': [
        "could potentially be related to",
        "one possible explanation is",
        "it's worth considering whether",
        "some analysts suggest",
        "one interpretation is that",
        "there may be a connection to",
        "it's possible that",
        "one hypothesis is",
    ],
}


# =============================================================================
# UNCERTAINTY ACKNOWLEDGMENT PHRASES
# =============================================================================

UNCERTAINTY_PHRASES: List[str] = [
    "though other factors may also be at play",
    "although the relationship is complex",
    "while acknowledging uncertainty",
    "though causation is difficult to establish",
    "though multiple factors likely contribute",
    "while recognizing this is just one interpretation",
    "though the timing and magnitude remain uncertain",
    "although other explanations are possible",
    "while noting that economic relationships can shift",
    "though historical patterns don't always repeat",
]


# =============================================================================
# OVERCONFIDENT PHRASES TO REPLACE
# =============================================================================

# Phrases that sound too certain about causation
# Maps overconfident phrase -> (confidence_level, replacement_type)
# replacement_type: 'standard' for typical hedging, 'forward' for future predictions
OVERCONFIDENT_PHRASES: Dict[str, str] = {
    # Original phrase -> confidence level to use for replacement
    # Standard backward-looking causal claims
    "reflects the": "medium_confidence",
    "reflects": "medium_confidence",
    "is due to": "medium_confidence",
    "is caused by": "medium_confidence",
    "shows that": "high_confidence",
    "demonstrates that": "high_confidence",
    "proves that": "low_confidence",  # Almost nothing in economics "proves"
    "confirms that": "high_confidence",
    "indicates that": "high_confidence",
    "results from": "medium_confidence",
    "is a result of": "medium_confidence",
    "stems from": "medium_confidence",
    "is driven by": "medium_confidence",
    "driven by": "medium_confidence",
    "because of": "medium_confidence",
    "as a result of": "medium_confidence",
    "owing to": "medium_confidence",
    "thanks to": "medium_confidence",
    "leads to": "medium_confidence",  # Forward causation claims
    "will cause": "low_confidence",
    "will result in": "low_confidence",
    "will lead to": "low_confidence",
}

# Forward-looking phrases need special replacement text
FORWARD_LOOKING_REPLACEMENTS: Dict[str, str] = {
    "will cause": "could potentially lead to",
    "will result in": "may potentially contribute to",
    "will lead to": "could eventually result in",
    "leads to": "may lead to",
}


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def get_hedging_phrase(confidence: str = 'medium_confidence') -> str:
    """
    Get a random hedging phrase for the specified confidence level.

    Args:
        confidence: One of 'high_confidence', 'medium_confidence', 'low_confidence',
                   or shorthand 'high', 'medium', 'low'

    Returns:
        A hedging phrase appropriate for the confidence level.

    Example:
        >>> phrase = get_hedging_phrase('medium')
        >>> print(phrase)
        'may reflect'
    """
    # Normalize confidence level
    confidence_map = {
        'high': 'high_confidence',
        'medium': 'medium_confidence',
        'low': 'low_confidence',
        'high_confidence': 'high_confidence',
        'medium_confidence': 'medium_confidence',
        'low_confidence': 'low_confidence',
    }

    normalized = confidence_map.get(confidence.lower(), 'medium_confidence')
    phrases = HEDGING_PHRASES.get(normalized, HEDGING_PHRASES['medium_confidence'])

    return random.choice(phrases)


def get_uncertainty_phrase() -> str:
    """
    Get a random uncertainty acknowledgment phrase.

    Returns:
        An uncertainty acknowledgment phrase.

    Example:
        >>> phrase = get_uncertainty_phrase()
        >>> print(phrase)
        'though other factors may also be at play'
    """
    return random.choice(UNCERTAINTY_PHRASES)


def hedge_causal_claim(
    claim: str,
    confidence: str = 'medium',
    add_uncertainty: bool = True,
    specific_cause: Optional[str] = None,
) -> str:
    """
    Add appropriate hedging to a causal claim.

    This function transforms overconfident causal statements into appropriately
    hedged claims that acknowledge uncertainty. It:
    1. Detects overconfident phrases and replaces them with hedged alternatives
    2. Optionally appends an uncertainty acknowledgment

    Args:
        claim: The original causal claim to hedge.
        confidence: Confidence level - 'high', 'medium', or 'low'.
        add_uncertainty: Whether to append an uncertainty acknowledgment.
        specific_cause: Optional specific cause to reference in the hedging.

    Returns:
        The hedged version of the claim.

    Examples:
        Input:  "The rise in unemployment reflects Fed rate hikes"
        Output: "The rise in unemployment may reflect Fed rate hikes,
                though other factors could also be at play"

        Input:  "Inflation is caused by supply chain disruptions"
        Output: "Inflation could be influenced by supply chain disruptions,
                while acknowledging uncertainty"

        Input:  "Strong GDP shows the economy is healthy"
        Output: "Strong GDP is consistent with a healthy economy,
                though causation is difficult to establish"
    """
    hedged_claim = claim
    found_overconfident = False

    # Look for overconfident phrases and replace them
    # Sort by length (longest first) to match more specific phrases first
    sorted_phrases = sorted(OVERCONFIDENT_PHRASES.keys(), key=len, reverse=True)

    for overconfident in sorted_phrases:
        if overconfident.lower() in claim.lower():
            suggested_confidence = OVERCONFIDENT_PHRASES[overconfident]

            # Check if this is a forward-looking phrase with special handling
            if overconfident in FORWARD_LOOKING_REPLACEMENTS:
                replacement = FORWARD_LOOKING_REPLACEMENTS[overconfident]
            else:
                # Use the provided confidence level, or fall back to the suggested one
                effective_confidence = confidence or suggested_confidence
                replacement = get_hedging_phrase(effective_confidence)

            # Replace the overconfident phrase (case-insensitive)
            pattern = re.compile(re.escape(overconfident), re.IGNORECASE)
            hedged_claim = pattern.sub(replacement, hedged_claim, count=1)
            found_overconfident = True
            break  # Only replace the first match

    # If no overconfident phrase was found, prepend a hedging phrase
    if not found_overconfident:
        hedging_phrase = get_hedging_phrase(confidence)

        # Check if the claim starts with common patterns
        if claim.lower().startswith("the "):
            # "The rise reflects X" -> "The rise may reflect X"
            # Insert hedging after the subject
            parts = claim.split(" ", 2)  # Split into at most 3 parts
            if len(parts) >= 3:
                subject = f"{parts[0]} {parts[1]}"  # "The rise"
                rest = parts[2]  # "reflects X" or similar
                hedged_claim = f"{subject} {hedging_phrase} {rest}"
            else:
                hedged_claim = f"This {hedging_phrase} {claim.lower()}"
        else:
            # Generic case: prepend "This [hedge] [claim]"
            hedged_claim = f"This {hedging_phrase} {claim.lower()}"

    # Add uncertainty acknowledgment if requested
    if add_uncertainty:
        # Clean up any trailing punctuation before adding the uncertainty phrase
        hedged_claim = hedged_claim.rstrip('.')
        uncertainty = get_uncertainty_phrase()
        hedged_claim = f"{hedged_claim}, {uncertainty}."
    elif not hedged_claim.endswith('.'):
        hedged_claim = f"{hedged_claim}."

    return hedged_claim


def transform_overconfident_language(text: str, confidence: str = 'medium') -> str:
    """
    Transform all overconfident causal language in a text passage.

    This is useful for post-processing generated explanations to ensure
    they maintain appropriate epistemic humility throughout.

    Args:
        text: The text passage to transform.
        confidence: Default confidence level to use for transformations.

    Returns:
        The transformed text with hedged language.

    Example:
        >>> text = "Rising rates caused the slowdown. This shows Fed policy works."
        >>> hedged = transform_overconfident_language(text, confidence='medium')
        >>> print(hedged)
        "Rising rates may have contributed to the slowdown. This is consistent
        with Fed policy having an effect."
    """
    result = text

    # Sort by length (longest first) to avoid partial matches
    sorted_phrases = sorted(OVERCONFIDENT_PHRASES.keys(), key=len, reverse=True)

    for overconfident in sorted_phrases:
        if overconfident.lower() in result.lower():
            # Check if this is a forward-looking phrase with special handling
            if overconfident in FORWARD_LOOKING_REPLACEMENTS:
                replacement = FORWARD_LOOKING_REPLACEMENTS[overconfident]
            else:
                suggested_confidence = OVERCONFIDENT_PHRASES[overconfident]
                effective_confidence = confidence or suggested_confidence
                replacement = get_hedging_phrase(effective_confidence)

            # Replace all occurrences (case-insensitive)
            pattern = re.compile(re.escape(overconfident), re.IGNORECASE)
            result = pattern.sub(replacement, result)

    return result


def build_causal_narrative(
    observation: str,
    potential_cause: str,
    confidence: str = 'medium',
    supporting_evidence: Optional[List[str]] = None,
    time_lag: Optional[str] = None,
) -> str:
    """
    Build a properly hedged causal narrative connecting an observation to a cause.

    This is useful for constructing explanations in economic briefings where
    you want to suggest a causal relationship while maintaining appropriate
    uncertainty.

    Args:
        observation: What we observe (e.g., "unemployment rising to 4.2%")
        potential_cause: The suggested cause (e.g., "Fed rate hikes")
        confidence: How confident we are in this explanation
        supporting_evidence: Optional list of supporting data points
        time_lag: Optional time lag to mention (e.g., "12-18 months")

    Returns:
        A properly hedged narrative paragraph.

    Example:
        >>> narrative = build_causal_narrative(
        ...     observation="The unemployment rate rising from 3.7% to 4.2%",
        ...     potential_cause="the lagged effect of Fed rate hikes",
        ...     confidence='medium',
        ...     time_lag="12-18 months"
        ... )
        >>> print(narrative)
        "The unemployment rate rising from 3.7% to 4.2% may reflect the lagged
        effect of Fed rate hikes. Economic theory suggests monetary policy
        typically affects labor markets with a lag of 12-18 months, though
        other factors could also be at play."
    """
    hedging_phrase = get_hedging_phrase(confidence)
    uncertainty_phrase = get_uncertainty_phrase()

    # Build the main claim
    narrative_parts = [f"{observation} {hedging_phrase} {potential_cause}."]

    # Add time lag context if provided
    if time_lag:
        narrative_parts.append(
            f"Economic theory suggests this relationship typically operates "
            f"with a lag of {time_lag}."
        )

    # Add supporting evidence if provided
    if supporting_evidence:
        evidence_intro = "This interpretation is supported by" if confidence == 'high' else "Supporting data includes"
        evidence_list = "; ".join(supporting_evidence)
        narrative_parts.append(f"{evidence_intro}: {evidence_list}.")

    # Add uncertainty acknowledgment
    narrative_parts.append(f"However, {uncertainty_phrase}.")

    return " ".join(narrative_parts)


def get_confidence_for_claim(
    data_points: int = 1,
    historical_precedent: bool = False,
    multiple_sources: bool = False,
    established_theory: bool = False,
) -> str:
    """
    Determine appropriate confidence level based on supporting evidence.

    This helper function provides guidance on what confidence level to use
    based on the strength of the evidence.

    Args:
        data_points: Number of independent data points supporting the claim
        historical_precedent: Whether this pattern has occurred before
        multiple_sources: Whether multiple independent data sources agree
        established_theory: Whether this aligns with established economic theory

    Returns:
        Recommended confidence level: 'high', 'medium', or 'low'

    Example:
        >>> confidence = get_confidence_for_claim(
        ...     data_points=3,
        ...     historical_precedent=True,
        ...     established_theory=True
        ... )
        >>> print(confidence)
        'high'
    """
    score = 0

    # Score the evidence
    score += min(data_points, 3)  # Cap at 3 points
    score += 2 if historical_precedent else 0
    score += 2 if multiple_sources else 0
    score += 2 if established_theory else 0

    # Determine confidence
    if score >= 7:
        return 'high'
    elif score >= 4:
        return 'medium'
    else:
        return 'low'


# =============================================================================
# CAUSAL CHAIN HELPERS
# =============================================================================

def describe_transmission_mechanism(
    starting_point: str,
    ending_point: str,
    mechanism_steps: List[str],
    confidence: str = 'medium',
) -> str:
    """
    Describe a causal transmission mechanism with appropriate hedging.

    Useful for explaining how policy changes propagate through the economy
    (e.g., how Fed rate hikes eventually affect unemployment).

    Args:
        starting_point: The initial cause (e.g., "Fed rate hikes")
        ending_point: The final effect (e.g., "rising unemployment")
        mechanism_steps: Intermediate steps in the causal chain
        confidence: Overall confidence in this mechanism

    Returns:
        A hedged description of the transmission mechanism.

    Example:
        >>> description = describe_transmission_mechanism(
        ...     starting_point="Fed rate hikes",
        ...     ending_point="rising unemployment",
        ...     mechanism_steps=[
        ...         "higher borrowing costs for businesses",
        ...         "reduced investment and hiring",
        ...         "slower job creation",
        ...     ],
        ...     confidence='medium'
        ... )
    """
    hedging_phrase = get_hedging_phrase(confidence)
    uncertainty_phrase = get_uncertainty_phrase()

    intro = f"{starting_point} {hedging_phrase} contribute to {ending_point}"

    if mechanism_steps:
        steps_text = ", which ".join(mechanism_steps)
        mechanism = f" through a chain of effects: {steps_text}."
    else:
        mechanism = "."

    caveat = f" This transmission mechanism is well-documented historically, {uncertainty_phrase}."

    return intro + mechanism + caveat


# =============================================================================
# CAUSAL CHAIN LOOKUP UTILITIES
# =============================================================================

def get_chains_by_category(category: str) -> List[CausalChain]:
    """
    Get all causal chains in a category.

    Categories:
    - 'fed_policy': Fed transmission mechanisms
    - 'labor': Labor market dynamics
    - 'inflation': Inflation dynamics
    - 'recession': Recession signals
    - 'consumer': Consumer behavior
    - 'international': Global linkages
    - 'markets': Financial market signals
    """
    category_prefixes = {
        'fed_policy': ['fed_hikes', 'fed_cuts'],
        'labor': ['tight_labor', 'quits', 'openings', 'claims', 'prime_age'],
        'inflation': ['shelter', 'goods_services', 'wage_price', 'energy', 'inflation_expect', 'supercore'],
        'recession': ['yield_curve', 'sahm', 'leading_indicators', 'credit_spread'],
        'consumer': ['sentiment', 'excess_savings', 'wealth_effect', 'credit_card'],
        'international': ['dollar', 'china', 'global_rate', 'oil_shock'],
        'markets': ['stock_market', 'vix'],
    }

    prefixes = category_prefixes.get(category, [])
    return [chain for chain_id, chain in CAUSAL_CHAINS.items()
            if any(chain_id.startswith(p) for p in prefixes)]


def get_chains_for_series(series_id: str) -> List[CausalChain]:
    """
    Get all causal chains that reference a given FRED series.

    This is useful for explaining why a particular indicator matters.
    """
    return [chain for chain in CAUSAL_CHAINS.values()
            if series_id in chain.relevant_series]


def get_related_chains(chain_id: str) -> List[CausalChain]:
    """Get chains related to a given chain (by shared series)."""
    if chain_id not in CAUSAL_CHAINS:
        return []

    base_chain = CAUSAL_CHAINS[chain_id]
    related = []

    for other_id, other_chain in CAUSAL_CHAINS.items():
        if other_id == chain_id:
            continue
        shared_series = set(base_chain.relevant_series) & set(other_chain.relevant_series)
        if shared_series:
            related.append(other_chain)

    return related


def get_all_relevant_series() -> List[str]:
    """Get all unique FRED series IDs referenced across all causal chains."""
    all_series = set()
    for chain in CAUSAL_CHAINS.values():
        all_series.update(chain.relevant_series)
    return sorted(list(all_series))


# =============================================================================
# PATTERN DETECTION
# =============================================================================

@dataclass
class ActivePattern:
    """A causal pattern that appears to be active given current data."""
    chain: CausalChain
    confidence: float           # 0.0 to 1.0
    evidence: List[str]         # What data supports this
    current_values: Dict[str, float]  # Relevant series and their values
    status: str                 # 'early', 'active', 'late', 'reversing'
    implication: str            # What this means going forward


def detect_causal_patterns(data_context: Dict) -> List[ActivePattern]:
    """
    Detect which causal patterns are active given the current data.

    This function examines the data and identifies which causal chains
    appear to be in motion. It looks for:
    - Series levels that trigger chains
    - Trends that suggest chains are progressing
    - Combinations of factors that activate conditional chains

    Args:
        data_context: Dictionary with structure:
            {
                'series_id': {
                    'value': float,         # Latest value
                    'yoy_change': float,    # Year-over-year percent change
                    'mom_change': float,    # Month-over-month change
                    'trend': str,           # 'rising', 'falling', 'stable'
                }
            }

    Returns:
        List of ActivePattern objects, sorted by confidence (highest first).
    """
    active_patterns = []

    # Helper functions
    def get_val(series_id: str, field: str = 'value') -> Optional[float]:
        if series_id not in data_context:
            return None
        return data_context[series_id].get(field)

    def get_trend(series_id: str) -> Optional[str]:
        if series_id not in data_context:
            return None
        return data_context[series_id].get('trend')

    # ==========================================================================
    # Fed Policy Transmission Detection
    # ==========================================================================

    fed_funds = get_val('FEDFUNDS')
    if fed_funds is not None and fed_funds >= 4.5:
        evidence = [f"Fed funds rate at {fed_funds:.2f}% (restrictive)"]
        confidence = 0.5
        current_values = {'FEDFUNDS': fed_funds}

        mortgage_rate = get_val('MORTGAGE30US')
        if mortgage_rate and mortgage_rate > 6.0:
            evidence.append(f"Mortgage rates elevated at {mortgage_rate:.2f}%")
            confidence += 0.2
            current_values['MORTGAGE30US'] = mortgage_rate

        inflation_trend = get_trend('CPIAUCSL')
        core_inflation = get_val('PCEPILFE', 'yoy_change')

        if inflation_trend == 'falling' or (core_inflation and core_inflation < 3.0):
            evidence.append(f"Inflation cooling (core PCE at {core_inflation or 'N/A'}%)")
            confidence += 0.15
            status = 'active'
            implication = (
                "Fed policy is working as intended. The transmission from high rates to lower "
                "inflation is underway. Watch for labor market effects in coming months."
            )
        else:
            status = 'early'
            implication = (
                "Fed has raised rates significantly but inflation has not yet fallen decisively. "
                "The typical 12-18 month lag means effects may still be coming."
            )

        if confidence > 0.5:
            active_patterns.append(ActivePattern(
                chain=CAUSAL_CHAINS['fed_hikes_inflation'],
                confidence=min(confidence, 0.95),
                evidence=evidence,
                current_values=current_values,
                status=status,
                implication=implication,
            ))

    # ==========================================================================
    # Labor Market Dynamics Detection
    # ==========================================================================

    unemployment = get_val('UNRATE')
    quits_rate = get_val('JTSQUR')
    wage_growth = get_val('CES0500000003', 'yoy_change')

    if unemployment is not None and unemployment < 4.5:
        evidence = [f"Unemployment at {unemployment:.1f}% (below NAIRU ~4.2%)"]
        confidence = 0.5
        current_values = {'UNRATE': unemployment}

        if quits_rate and quits_rate > 2.3:
            evidence.append(f"Quits rate elevated at {quits_rate:.1f}% (workers confident)")
            confidence += 0.2
            current_values['JTSQUR'] = quits_rate

        if wage_growth and wage_growth > 4.0:
            evidence.append(f"Wage growth at {wage_growth:.1f}% YoY (elevated)")
            confidence += 0.2
            current_values['CES0500000003'] = wage_growth
            status = 'active'
            implication = (
                "Labor market tightness is translating into wage pressure. This is the "
                "tight_labor_wages chain in action. Will sustain services inflation."
            )
        else:
            status = 'early'
            implication = (
                "Labor market is tight but wage pressure is contained. Either productivity "
                "is offsetting, or workers are not fully using their leverage (yet)."
            )

        if confidence > 0.5:
            active_patterns.append(ActivePattern(
                chain=CAUSAL_CHAINS['tight_labor_wages'],
                confidence=min(confidence, 0.9),
                evidence=evidence,
                current_values=current_values,
                status=status,
                implication=implication,
            ))

    # Sahm Rule detection
    sahm = get_val('SAHMREALTIME')
    if sahm is not None:
        evidence = [f"Sahm Rule indicator at {sahm:.2f}"]
        current_values = {'SAHMREALTIME': sahm}

        if sahm >= 0.5:
            confidence = 0.9
            status = 'active'
            implication = (
                "CRITICAL: The Sahm Rule has triggered. This has correctly signaled every "
                "recession since 1970. Unemployment is accelerating in a pattern consistent "
                "with recession."
            )
            active_patterns.append(ActivePattern(
                chain=CAUSAL_CHAINS['sahm_rule_mechanics'],
                confidence=confidence,
                evidence=evidence,
                current_values=current_values,
                status=status,
                implication=implication,
            ))
        elif sahm >= 0.3:
            confidence = 0.6
            status = 'early'
            implication = (
                "Sahm Rule approaching trigger level. Unemployment is rising faster than normal. "
                "If this continues to 0.5, it would signal recession has likely begun."
            )
            active_patterns.append(ActivePattern(
                chain=CAUSAL_CHAINS['sahm_rule_mechanics'],
                confidence=confidence,
                evidence=evidence,
                current_values=current_values,
                status=status,
                implication=implication,
            ))

    # ==========================================================================
    # Yield Curve / Recession Signal Detection
    # ==========================================================================

    spread_10y2y = get_val('T10Y2Y')
    spread_10y3m = get_val('T10Y3M')
    primary_spread = spread_10y3m if spread_10y3m is not None else spread_10y2y

    if primary_spread is not None:
        current_values = {}
        if spread_10y2y is not None:
            current_values['T10Y2Y'] = spread_10y2y
        if spread_10y3m is not None:
            current_values['T10Y3M'] = spread_10y3m

        if primary_spread < 0:
            confidence = 0.7 if primary_spread < -0.5 else 0.6
            status = 'active'
            evidence = [f"Yield curve inverted at {primary_spread:.2f}%"]
            implication = (
                "Yield curve is inverted - the classic recession signal. Historically, recessions "
                "follow 12-18 months after inversions begin. Not a guarantee, but a strong warning."
            )
            active_patterns.append(ActivePattern(
                chain=CAUSAL_CHAINS['yield_curve_recession'],
                confidence=confidence,
                evidence=evidence,
                current_values=current_values,
                status=status,
                implication=implication,
            ))
        elif primary_spread < 0.25:
            confidence = 0.5
            status = 'early'
            evidence = [f"Yield curve flat at {primary_spread:.2f}%"]
            implication = (
                "Yield curve is nearly flat - a cautionary signal. If it inverts, recession watch "
                "would begin. Not yet a warning, but close."
            )
            active_patterns.append(ActivePattern(
                chain=CAUSAL_CHAINS['yield_curve_recession'],
                confidence=confidence,
                evidence=evidence,
                current_values=current_values,
                status=status,
                implication=implication,
            ))

    # ==========================================================================
    # Inflation Dynamics Detection
    # ==========================================================================

    # Shelter lag pattern
    cpi_shelter_yoy = get_val('CUSR0000SAH1', 'yoy_change')
    zillow_rent_yoy = get_val('zillow_zori_national', 'yoy_change')

    if cpi_shelter_yoy is not None and zillow_rent_yoy is not None:
        gap = cpi_shelter_yoy - zillow_rent_yoy
        evidence = [
            f"Official shelter CPI at {cpi_shelter_yoy:.1f}% YoY",
            f"Market rents (Zillow) at {zillow_rent_yoy:.1f}% YoY",
            f"Gap of {gap:.1f} percentage points"
        ]
        current_values = {
            'CUSR0000SAH1': cpi_shelter_yoy,
            'zillow_zori_national': zillow_rent_yoy,
        }

        if gap > 1.0:
            confidence = 0.85 if gap > 2.0 else 0.7
            status = 'active'
            implication = (
                f"Shelter CPI is {gap:.1f} points higher than market rents. This gap will close "
                "over the next 12-18 months as old expensive leases roll off. Expect shelter "
                "CPI to fall significantly, which will pull down overall inflation."
            )
            active_patterns.append(ActivePattern(
                chain=CAUSAL_CHAINS['shelter_lag'],
                confidence=confidence,
                evidence=evidence,
                current_values=current_values,
                status=status,
                implication=implication,
            ))

    # Goods vs services split
    goods_inflation = get_val('CUSR0000SAC', 'yoy_change')
    services_inflation = get_val('CUSR0000SAS', 'yoy_change')

    if goods_inflation is not None and services_inflation is not None:
        if goods_inflation < 0 and services_inflation > 3:
            evidence = [
                f"Goods inflation at {goods_inflation:.1f}% YoY",
                f"Services inflation at {services_inflation:.1f}% YoY",
            ]
            current_values = {
                'CUSR0000SAC': goods_inflation,
                'CUSR0000SAS': services_inflation,
            }
            implication = (
                "Classic goods deflation / services sticky pattern. Goods prices are falling "
                "(supply chains healed) but services remain elevated (wage-driven). The last "
                "mile of disinflation will be slow."
            )
            active_patterns.append(ActivePattern(
                chain=CAUSAL_CHAINS['goods_services_split'],
                confidence=0.85,
                evidence=evidence,
                current_values=current_values,
                status='active',
                implication=implication,
            ))

    # Inflation expectations check
    expectations_5y5y = get_val('T5YIFR')
    if expectations_5y5y is not None and (expectations_5y5y > 2.5 or expectations_5y5y < 1.8):
        evidence = [f"5Y5Y inflation expectations at {expectations_5y5y:.2f}%"]
        current_values = {'T5YIFR': expectations_5y5y}

        if expectations_5y5y > 2.7:
            status = 'warning'
            implication = (
                f"Long-term inflation expectations at {expectations_5y5y:.2f}% are drifting "
                "above the Fed's comfort zone. Risk of expectations becoming unanchored."
            )
            confidence = 0.7
        else:
            status = 'anchored'
            implication = "Long-term inflation expectations well-anchored near 2%."
            confidence = 0.5

        active_patterns.append(ActivePattern(
            chain=CAUSAL_CHAINS['inflation_expectations_anchor'],
            confidence=confidence,
            evidence=evidence,
            current_values=current_values,
            status=status,
            implication=implication,
        ))

    # ==========================================================================
    # Consumer Dynamics Detection
    # ==========================================================================

    consumer_sentiment = get_val('UMCSENT')
    if consumer_sentiment is not None and consumer_sentiment < 70:
        evidence = [f"Consumer sentiment at {consumer_sentiment:.0f}"]
        current_values = {'UMCSENT': consumer_sentiment}
        spending_trend = get_trend('PCE') or get_trend('RSXFS')

        if consumer_sentiment < 60:
            if spending_trend == 'falling':
                status = 'active'
                implication = (
                    "Low sentiment is translating into weaker spending. Consumers are worried "
                    "and pulling back."
                )
                confidence = 0.8
            else:
                status = 'divergent'
                implication = (
                    f"Sentiment is low ({consumer_sentiment:.0f}) but spending holds up - likely "
                    "due to excess savings or wealth effects. This divergence may not last."
                )
                confidence = 0.6
        else:
            status = 'caution'
            implication = "Consumer sentiment below average. Not alarming, but cautious."
            confidence = 0.5

        active_patterns.append(ActivePattern(
            chain=CAUSAL_CHAINS['sentiment_spending'],
            confidence=confidence,
            evidence=evidence,
            current_values=current_values,
            status=status,
            implication=implication,
        ))

    # Sort by confidence
    active_patterns.sort(key=lambda x: x.confidence, reverse=True)

    return active_patterns


# =============================================================================
# RELATIONSHIP EXPLANATION
# =============================================================================

# Mapping of indicator pairs to their causal explanations
INDICATOR_RELATIONSHIPS: Dict[Tuple[str, str], str] = {
    # Fed policy and inflation
    ('FEDFUNDS', 'CPIAUCSL'): 'fed_hikes_inflation',
    ('FEDFUNDS', 'PCEPILFE'): 'fed_hikes_inflation',
    ('FEDFUNDS', 'UNRATE'): 'fed_hikes_unemployment',
    ('FEDFUNDS', 'MORTGAGE30US'): 'fed_hikes_housing',
    ('FEDFUNDS', 'DTWEXBGS'): 'fed_hikes_dollar',
    # Yield curve
    ('T10Y2Y', 'GDPC1'): 'yield_curve_recession',
    ('T10Y3M', 'GDPC1'): 'yield_curve_recession',
    ('DGS10', 'DGS2'): 'yield_curve_recession',
    # Labor market
    ('UNRATE', 'CES0500000003'): 'tight_labor_wages',
    ('UNRATE', 'ECIWAG'): 'tight_labor_wages',
    ('JTSQUR', 'UNRATE'): 'quits_rate_signal',
    ('ICSA', 'UNRATE'): 'claims_spike_warning',
    # Inflation dynamics
    ('CUSR0000SAH1', 'CPIAUCSL'): 'shelter_lag',
    ('CES0500000003', 'CUSR0000SAS'): 'wage_price_spiral',
    ('DCOILWTICO', 'CPIAUCSL'): 'energy_pass_through',
    ('T5YIFR', 'CPIAUCSL'): 'inflation_expectations_anchor',
    # Consumer
    ('UMCSENT', 'PCE'): 'sentiment_spending',
    ('UMCSENT', 'RSXFS'): 'sentiment_spending',
    ('SP500', 'PCE'): 'wealth_effect_spending',
    ('CSUSHPINSA', 'PCE'): 'wealth_effect_spending',
    # International
    ('DTWEXBGS', 'BOPGSTB'): 'dollar_trade_impact',
    ('DTWEXBGS', 'MANEMP'): 'dollar_trade_impact',
}


def explain_relationship(
    indicator1: str,
    indicator2: str,
    data: Dict,
) -> Optional[str]:
    """
    Explain why two indicators are related.

    This function takes two indicator series and explains the causal mechanism
    connecting them, using current data to make the explanation concrete.

    Args:
        indicator1: First FRED series ID
        indicator2: Second FRED series ID
        data: Data dictionary with series values and changes

    Returns:
        Human-readable explanation of the relationship, or None if no
        known relationship exists.
    """
    # Check both orderings
    chain_id = INDICATOR_RELATIONSHIPS.get((indicator1, indicator2))
    if chain_id is None:
        chain_id = INDICATOR_RELATIONSHIPS.get((indicator2, indicator1))

    if chain_id is None:
        # Try to find indirect through shared chains
        chains_1 = get_chains_for_series(indicator1)
        chains_2 = get_chains_for_series(indicator2)
        common = [c for c in chains_1 if c in chains_2]
        if common:
            chain = common[0]
        else:
            return None
    else:
        chain = CAUSAL_CHAINS[chain_id]

    # Get current values for context
    def get_display_value(series_id: str) -> str:
        if series_id not in data:
            return "N/A"
        val = data[series_id].get('value')
        if val is None:
            return "N/A"
        if 'rate' in series_id.lower() or series_id in ['UNRATE', 'FEDFUNDS']:
            return f"{val:.2f}%"
        return f"{val:,.1f}"

    val1 = get_display_value(indicator1)
    val2 = get_display_value(indicator2)

    explanation_parts = [
        f"WHY {indicator1} AND {indicator2} MOVE TOGETHER:",
        "",
        f"Current values: {indicator1} at {val1}, {indicator2} at {val2}",
        "",
        f"The causal mechanism: {chain.cause} -> {chain.effect}",
        "",
        chain.mechanism,
        "",
        f"Typical lag: {chain.lag}",
        "",
    ]

    if chain.key_insight:
        explanation_parts.append(f"Key insight: {chain.key_insight}")

    return "\n".join(explanation_parts)


# =============================================================================
# FORWARD IMPLICATIONS
# =============================================================================

def get_forward_implications(
    data_context: Dict,
    active_chains: Optional[List[ActivePattern]] = None,
) -> List[str]:
    """
    Given current conditions and active causal chains, what should we expect next?

    Args:
        data_context: Current data (same format as detect_causal_patterns)
        active_chains: Result from detect_causal_patterns() or None to auto-detect

    Returns:
        List of forward-looking implications, prioritized by importance.
    """
    if active_chains is None:
        active_chains = detect_causal_patterns(data_context)

    implications = []

    for pattern in active_chains:
        if pattern.confidence < 0.5:
            continue

        confidence_label = "HIGH CONFIDENCE" if pattern.confidence > 0.7 else "MODERATE CONFIDENCE"
        implications.append(
            f"[{confidence_label}] {pattern.implication} "
            f"(typical lag: {pattern.chain.lag})"
        )

    return implications[:5]  # Top 5


# =============================================================================
# NARRATIVE BUILDER (ENHANCED VERSION)
# =============================================================================

def build_full_causal_narrative(
    query: str,
    data_context: Dict,
    series_data: Optional[Dict] = None,
) -> str:
    """
    Build a narrative that explains WHY, not just WHAT.

    This is the main entry point for generating causal explanations. It:
    1. Identifies what's happening
    2. Explains WHY it's happening (the causal mechanism)
    3. Projects what should happen next

    Args:
        query: The user's question
        data_context: Processed data with values, changes, trends
        series_data: Raw series data (optional)

    Returns:
        A narrative explanation suitable for display to users.
    """
    patterns = detect_causal_patterns(data_context)

    narrative_parts = []
    narrative_parts.append("=" * 70)
    narrative_parts.append("WHAT'S HAPPENING AND WHY")
    narrative_parts.append("=" * 70)
    narrative_parts.append("")

    if not patterns:
        narrative_parts.append(
            "The economic indicators show relatively stable conditions. No strong causal "
            "patterns are currently active, suggesting the economy is in equilibrium."
        )
    else:
        high_confidence = [p for p in patterns if p.confidence >= 0.7]
        moderate_confidence = [p for p in patterns if 0.5 <= p.confidence < 0.7]

        if high_confidence:
            narrative_parts.append("CLEAR DYNAMICS IN MOTION:")
            narrative_parts.append("")
            for pattern in high_confidence[:3]:
                narrative_parts.append(f"* {pattern.chain.cause} -> {pattern.chain.effect}")
                narrative_parts.append(f"  Status: {pattern.status.upper()}")
                narrative_parts.append(f"  Evidence: {', '.join(pattern.evidence)}")
                narrative_parts.append(f"  Lag: {pattern.chain.lag}")
                narrative_parts.append("")
                narrative_parts.append(f"  {pattern.implication}")
                narrative_parts.append("")

        if moderate_confidence:
            narrative_parts.append("ALSO WORTH WATCHING:")
            narrative_parts.append("")
            for pattern in moderate_confidence[:2]:
                narrative_parts.append(f"* {pattern.chain.cause} -> {pattern.chain.effect}")
                narrative_parts.append(f"  {pattern.implication}")
                narrative_parts.append("")

    implications = get_forward_implications(data_context, patterns)
    if implications:
        narrative_parts.append("-" * 70)
        narrative_parts.append("WHAT TO EXPECT NEXT")
        narrative_parts.append("-" * 70)
        narrative_parts.append("")
        for impl in implications:
            narrative_parts.append(f"* {impl}")
            narrative_parts.append("")

    if patterns:
        top_pattern = patterns[0]
        if top_pattern.chain.key_insight:
            narrative_parts.append("-" * 70)
            narrative_parts.append("THE KEY INSIGHT")
            narrative_parts.append("-" * 70)
            narrative_parts.append("")
            narrative_parts.append(top_pattern.chain.key_insight)

    return "\n".join(narrative_parts)


# =============================================================================
# TESTS
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("CAUSAL REASONING ENGINE - COMPREHENSIVE TESTS")
    print("=" * 70)

    # =========================================================================
    # CAUSAL CHAINS TESTS
    # =========================================================================

    # Test 1: List all causal chains
    print("\n1. AVAILABLE CAUSAL CHAINS")
    print("-" * 40)
    for chain_id, chain in list(CAUSAL_CHAINS.items())[:5]:  # Show first 5
        print(f"\n  {chain_id}:")
        print(f"    {chain.cause} -> {chain.effect}")
        print(f"    Lag: {chain.lag} | Strength: {chain.strength.value}")
    print(f"\n  ... and {len(CAUSAL_CHAINS) - 5} more chains")
    print(f"\n  Total chains: {len(CAUSAL_CHAINS)}")

    # Test 2: Chains by category
    print("\n\n2. CHAINS BY CATEGORY")
    print("-" * 40)
    for category in ['fed_policy', 'labor', 'inflation', 'recession', 'consumer', 'international', 'markets']:
        chains = get_chains_by_category(category)
        print(f"  {category}: {len(chains)} chains")
        for c in chains[:2]:  # Show first 2 in each category
            print(f"    - {c.id}")

    # Test 3: Pattern detection with mock data
    print("\n\n3. PATTERN DETECTION (SIMULATED DATA)")
    print("-" * 40)

    mock_data = {
        'FEDFUNDS': {'value': 4.75, 'trend': 'stable'},
        'MORTGAGE30US': {'value': 6.8, 'trend': 'stable'},
        'CPIAUCSL': {'value': None, 'yoy_change': 2.8, 'trend': 'falling'},
        'PCEPILFE': {'value': None, 'yoy_change': 2.6, 'trend': 'falling'},
        'UNRATE': {'value': 4.2, 'trend': 'stable'},
        'CES0500000003': {'value': None, 'yoy_change': 3.8, 'trend': 'falling'},
        'JTSQUR': {'value': 2.1, 'trend': 'falling'},
        'T10Y2Y': {'value': 0.15, 'trend': 'rising'},
        'T10Y3M': {'value': 0.10, 'trend': 'rising'},
        'CUSR0000SAH1': {'value': None, 'yoy_change': 4.5, 'trend': 'falling'},
        'zillow_zori_national': {'value': None, 'yoy_change': 2.8, 'trend': 'stable'},
        'CUSR0000SAC': {'value': None, 'yoy_change': -0.8, 'trend': 'stable'},
        'CUSR0000SAS': {'value': None, 'yoy_change': 4.2, 'trend': 'falling'},
        'T5YIFR': {'value': 2.3, 'trend': 'stable'},
        'UMCSENT': {'value': 72, 'trend': 'rising'},
        'SAHMREALTIME': {'value': 0.2, 'trend': 'stable'},
    }

    print("Simulated conditions:")
    print("  - Fed funds at 4.75% (restrictive)")
    print("  - Core PCE at 2.6% (falling)")
    print("  - Unemployment at 4.2% (stable)")
    print("  - Shelter CPI 4.5% vs market rents 2.8%")
    print()

    patterns = detect_causal_patterns(mock_data)

    print(f"Detected {len(patterns)} active patterns:\n")
    for p in patterns[:3]:  # Show top 3
        print(f"  CHAIN: {p.chain.id}")
        print(f"  Confidence: {p.confidence:.0%}")
        print(f"  Status: {p.status}")
        print(f"  Implication: {p.implication[:80]}...")
        print()

    # Test 4: Full causal narrative
    print("\n4. FULL CAUSAL NARRATIVE")
    print("-" * 40)
    narrative = build_full_causal_narrative("How is the economy doing?", mock_data)
    print(narrative[:1500] + "..." if len(narrative) > 1500 else narrative)

    # Test 5: Relationship explanation
    print("\n\n5. RELATIONSHIP EXPLANATION")
    print("-" * 40)
    explanation = explain_relationship('FEDFUNDS', 'CPIAUCSL', mock_data)
    if explanation:
        print(explanation[:600] + "..." if len(explanation) > 600 else explanation)

    # Test 6: Forward implications
    print("\n\n6. FORWARD IMPLICATIONS")
    print("-" * 40)
    implications = get_forward_implications(mock_data, patterns)
    for impl in implications:
        print(f"  * {impl[:100]}...")
        print()

    # Test 7: Get all series used by chains
    print("\n7. SERIES REQUIRED BY CAUSAL CHAINS")
    print("-" * 40)
    all_series = get_all_relevant_series()
    print(f"Total unique series: {len(all_series)}")
    print(f"Sample: {', '.join(all_series[:10])}...")

    # =========================================================================
    # HEDGING UTILITIES TESTS
    # =========================================================================

    print("\n\n" + "=" * 70)
    print("HEDGING UTILITIES TESTS")
    print("=" * 70)

    # Test 8: Basic hedging
    print("\n8. BASIC HEDGING TESTS")
    print("-" * 40)

    test_claims = [
        "The rise in unemployment reflects Fed rate hikes",
        "Strong GDP shows the economy is healthy",
    ]

    for claim in test_claims:
        hedged = hedge_causal_claim(claim, confidence='medium')
        print(f"\nOriginal: {claim}")
        print(f"Hedged:   {hedged}")

    # Test 9: Different confidence levels
    print("\n\n9. CONFIDENCE LEVEL TESTS")
    print("-" * 40)

    claim = "Rising unemployment reflects Fed policy"

    for conf in ['high', 'medium', 'low']:
        hedged = hedge_causal_claim(claim, confidence=conf, add_uncertainty=False)
        print(f"\n{conf.upper()} confidence: {hedged}")

    # Test 10: Build hedged narrative
    print("\n\n10. HEDGED CAUSAL NARRATIVE")
    print("-" * 40)

    narrative = build_causal_narrative(
        observation="The unemployment rate rising from 3.7% to 4.2%",
        potential_cause="the lagged effect of Fed rate hikes",
        confidence='medium',
        time_lag="12-18 months"
    )
    print(f"\n{narrative}")

    # Test 11: Transform overconfident text
    print("\n\n11. TRANSFORM OVERCONFIDENT TEXT")
    print("-" * 40)

    overconfident_text = "Rising rates will cause a recession."
    transformed = transform_overconfident_language(overconfident_text, confidence='medium')
    print(f"Original:    {overconfident_text}")
    print(f"Transformed: {transformed}")

    # Test 12: Transmission mechanism description
    print("\n\n12. TRANSMISSION MECHANISM")
    print("-" * 40)

    mechanism = describe_transmission_mechanism(
        starting_point="Fed rate hikes",
        ending_point="rising unemployment",
        mechanism_steps=[
            "higher borrowing costs for businesses",
            "reduced investment and expansion",
            "slower job creation and eventual layoffs",
        ],
        confidence='medium'
    )
    print(f"\n{mechanism}")

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)
