"""
MASTER ECONOMIC KNOWLEDGE BASE

This is the SINGLE SOURCE OF TRUTH for all economic reasoning in EconStats.
Every LLM prompt in the system should reference this module.

When we learn something new (e.g., "U-6 is too obscure for normal users"),
we add it HERE - not scattered across 15 different prompt strings.
"""

# =============================================================================
# WHAT NORMAL PEOPLE MEAN
# =============================================================================

QUERY_INTENT_RULES = """
## What Normal People Mean

When someone asks about:
- "unemployment" → They mean the standard unemployment rate (U-3). NEVER U-6, U-4, or other alternative measures unless explicitly asked.
- "inflation" → They mean year-over-year price change (CPI or PCE). NEVER the raw index number.
- "jobs" / "job market" → They mean nonfarm payrolls (PAYEMS) + unemployment rate. Show monthly changes, not total level.
- "the economy" → They want the big picture: GDP growth + unemployment + inflation. The "Holy Trinity."
- "interest rates" / "rates" → They mean Fed Funds + Treasury yields. Include yield curve context.
- "housing" → Home prices + mortgage rates + housing starts. The affordability picture.
- "gas prices" → Regular gasoline (GASREGW). Not crude oil unless they ask.
- "rent" → CPI rent (CUSR0000SEHA) and/or Zillow market rents. NOT interest rates.
- "wages" → Average hourly earnings (CES0500000003) or real median weekly earnings (LES1252881600Q).
- "recession" → Yield curve (T10Y2Y) + unemployment trend + GDP + leading indicators.
- "[State name] unemployment" → State-specific rate ({STATE_CODE}UR) compared to national (UNRATE).
"""

# =============================================================================
# DISPLAY RULES
# =============================================================================

DISPLAY_RULES = """
## How to Present Data

### For INDEX data (CPI, home prices, PCE):
- ALWAYS show year-over-year % change. Raw index values are meaningless to users.
- "CPI is 326" means NOTHING. "Prices are up 3.0% from a year ago" means everything.

### For RATE data (unemployment %, interest rates, Fed funds):
- Show the raw rate - it's already interpretable.
- Use percentage POINT changes: "up 0.7 percentage points"
- NEVER say "rising 9.1% year-over-year" for a rate that went from 7.7% to 8.4%.
  That's the % change OF the rate - confusing and misleading.

### For JOBS/PAYROLL data:
- Show monthly CHANGES: "added 175K jobs last month"
- NEVER show YoY % change of payroll levels: "up 1.2%" is meaningless for employment

### For STATE data:
- ALWAYS show alongside the national equivalent for comparison
- "Minnesota's 3.2% vs the national 4.1%" - this is the whole point

### For GDP:
- Show quarterly annualized growth rate (A191RL1Q225SBEA) as the primary measure
- Can supplement with YoY of real GDP level (GDPC1) for longer trend
- NEVER show nominal GDP without context

### General rules:
- NO jargon: "U-6", "basis points", "seasonally adjusted annual rate" - use plain English
- Context window: Compare to 1-5 years ago, not decades
- Always explain what a trend MEANS for people, not just what the number is
"""

# =============================================================================
# FRED SERIES KNOWLEDGE
# =============================================================================

# The ~200 most important FRED series organized by what they answer
SERIES_BY_TOPIC = {
    "jobs_employment": {
        "description": "Employment and labor market indicators",
        "primary": [
            {"id": "PAYEMS", "name": "Total Nonfarm Payrolls", "use_for": "Total jobs in the economy. Show MONTHLY CHANGES."},
            {"id": "UNRATE", "name": "Unemployment Rate (U-3)", "use_for": "THE standard unemployment rate. This is what people mean by 'unemployment'."},
            {"id": "JTSJOL", "name": "Job Openings (JOLTS)", "use_for": "Unfilled positions. High = strong labor demand."},
            {"id": "LNS12300060", "name": "Prime-Age Employment Ratio", "use_for": "Best single measure of labor market health. % of 25-54 year olds employed."},
            {"id": "CIVPART", "name": "Labor Force Participation Rate", "use_for": "% of population in labor force."},
            {"id": "ICSA", "name": "Initial Jobless Claims", "use_for": "Weekly leading indicator of layoffs. Most timely labor data."},
        ],
        "secondary": [
            {"id": "JTSQUR", "name": "Quits Rate", "use_for": "Workers voluntarily leaving. High = worker confidence."},
            {"id": "CES0500000003", "name": "Average Hourly Earnings", "use_for": "Wage growth for private workers."},
            {"id": "LES1252881600Q", "name": "Real Median Weekly Earnings", "use_for": "Inflation-adjusted middle-class wages."},
            {"id": "AWHMAN", "name": "Manufacturing Weekly Hours", "use_for": "Leading indicator - hours cut before layoffs."},
        ]
    },

    "inflation": {
        "description": "Price level and inflation indicators",
        "primary": [
            {"id": "CPIAUCSL", "name": "CPI (Headline)", "use_for": "Consumer price inflation. ALWAYS show as YoY %."},
            {"id": "CPILFESL", "name": "Core CPI", "use_for": "CPI excluding food & energy. Shows underlying trend."},
            {"id": "PCEPILFE", "name": "Core PCE", "use_for": "The Fed's PREFERRED inflation measure. This is what they target at 2%."},
        ],
        "secondary": [
            {"id": "CUSR0000SEHA", "name": "CPI: Rent of Primary Residence", "use_for": "What renters actually pay. Biggest CPI component."},
            {"id": "CUSR0000SAF1", "name": "CPI: Food", "use_for": "Grocery price inflation."},
            {"id": "GASREGW", "name": "Regular Gas Price", "use_for": "Pump prices. Most visible price to consumers."},
            {"id": "T10YIE", "name": "10-Year Breakeven Inflation", "use_for": "Market's inflation expectations."},
        ]
    },

    "growth_gdp": {
        "description": "Economic growth and output",
        "primary": [
            {"id": "A191RL1Q225SBEA", "name": "Real GDP Growth (Quarterly)", "use_for": "THE headline growth number. Quarterly annualized rate."},
            {"id": "GDPC1", "name": "Real GDP Level", "use_for": "Total economic output. Show YoY % change for trend."},
        ],
        "secondary": [
            {"id": "INDPRO", "name": "Industrial Production", "use_for": "Factory/mining/utility output."},
            {"id": "PCE", "name": "Personal Consumption", "use_for": "Consumer spending - 70% of GDP."},
            {"id": "DGORDER", "name": "Durable Goods Orders", "use_for": "Orders for long-lasting goods. Leading indicator."},
            {"id": "RSXFS", "name": "Retail Sales ex Food Services", "use_for": "Consumer spending on goods."},
        ]
    },

    "interest_rates": {
        "description": "Federal Reserve policy and bond market",
        "primary": [
            {"id": "FEDFUNDS", "name": "Federal Funds Rate", "use_for": "THE policy rate the Fed controls."},
            {"id": "DGS2", "name": "2-Year Treasury", "use_for": "Market's best guess of Fed policy over next 2 years."},
            {"id": "DGS10", "name": "10-Year Treasury", "use_for": "THE benchmark long-term rate. Drives mortgages."},
            {"id": "T10Y2Y", "name": "Yield Curve (10Y-2Y)", "use_for": "Negative = inverted = recession warning signal."},
        ],
        "secondary": [
            {"id": "MORTGAGE30US", "name": "30-Year Mortgage Rate", "use_for": "Home affordability benchmark."},
            {"id": "BAMLH0A0HYM2", "name": "High Yield Spread", "use_for": "Credit risk appetite. Widens in stress."},
            {"id": "WALCL", "name": "Fed Balance Sheet", "use_for": "QE/QT measure. Size of Fed's holdings."},
        ]
    },

    "housing": {
        "description": "Housing market indicators",
        "primary": [
            {"id": "CSUSHPINSA", "name": "Case-Shiller Home Price Index", "use_for": "National home prices. Show as YoY %."},
            {"id": "MORTGAGE30US", "name": "30-Year Mortgage Rate", "use_for": "Affordability driver."},
            {"id": "HOUST", "name": "Housing Starts", "use_for": "New construction activity."},
        ],
        "secondary": [
            {"id": "EXHOSLUSM495S", "name": "Existing Home Sales", "use_for": "Transaction volume."},
            {"id": "PERMIT", "name": "Building Permits", "use_for": "Future construction pipeline."},
            {"id": "MSPUS", "name": "Median Home Sale Price", "use_for": "Typical selling price."},
            {"id": "CUSR0000SEHA", "name": "CPI: Rent", "use_for": "Rental cost inflation."},
        ]
    },

    "consumer": {
        "description": "Consumer health and spending",
        "primary": [
            {"id": "UMCSENT", "name": "Consumer Sentiment", "use_for": "How consumers feel about the economy."},
            {"id": "RSXFS", "name": "Retail Sales", "use_for": "Consumer spending on goods."},
            {"id": "PSAVERT", "name": "Personal Savings Rate", "use_for": "% of income saved. Low = stretched consumers."},
        ],
        "secondary": [
            {"id": "DSPIC96", "name": "Real Disposable Income", "use_for": "After-tax income adjusted for inflation."},
            {"id": "TOTALSA", "name": "Vehicle Sales", "use_for": "Big-ticket consumer purchases."},
            {"id": "REVOLSL", "name": "Revolving Credit (Credit Cards)", "use_for": "Consumer borrowing levels."},
        ]
    },

    "trade_markets": {
        "description": "Trade and financial markets",
        "primary": [
            {"id": "DTWEXBGS", "name": "US Dollar Index", "use_for": "Dollar strength vs trading partners."},
            {"id": "BOPGSTB", "name": "Trade Balance", "use_for": "Exports minus imports."},
            {"id": "VIXCLS", "name": "VIX", "use_for": "Stock market volatility / fear gauge."},
        ],
    },
}

# =============================================================================
# STATE SERIES PATTERNS
# =============================================================================

STATE_SERIES_PATTERNS = """
## State-Level Data in FRED

FRED uses consistent naming patterns for state data:
- {STATE_CODE}UR = State unemployment rate (e.g., MNUR, TXUR, CAUR, NYUR, OHUR)
- {STATE_CODE}NA = State nonfarm payrolls (e.g., MNNA, TXNA, CANA)
- {STATE_CODE}NGSP = State GDP (e.g., MNNGSP, TXNGSP)
- {STATE_CODE}POP = State population

State codes: AL, AK, AZ, AR, CA, CO, CT, DE, FL, GA, HI, ID, IL, IN, IA, KS,
KY, LA, ME, MD, MA, MI, MN, MS, MO, MT, NE, NV, NH, NJ, NM, NY, NC, ND, OH,
OK, OR, PA, RI, SC, SD, TN, TX, UT, VT, VA, WA, WV, WI, WY, DC

CRITICAL: For ANY state query, ALWAYS include the national equivalent alongside
for comparison. "Minnesota at 3.2%" means nothing without "vs national 4.1%".
"""

# =============================================================================
# DEMOGRAPHIC SERIES
# =============================================================================

DEMOGRAPHIC_SERIES_KNOWLEDGE = """
## Demographic-Specific Data

CRITICAL: When a user asks about a specific demographic group, you MUST use
group-specific series. Using overall UNRATE for "Black workers" is WRONG.

- Black/African American: LNS14000006 (unemployment), LNS11300006 (participation), LNS12300006 (employment ratio)
- Hispanic/Latino: LNS14000009, LNS11300009, LNS12300009
- Asian: LNS14000004, LNS11300004, LNS12300004
- White: LNS14000003, LNS11300003, LNS12300003
- Women: LNS14000002, LNS11300002, LNS12300002
- Men: LNS14000001, LNS11300001, LNS12300001
- Youth (16-19): LNS14000012
- Veterans: LNS14049526
"""

# =============================================================================
# SECTOR SERIES
# =============================================================================

SECTOR_SERIES_KNOWLEDGE = """
## Sector-Specific Employment Data

When a user asks about a specific sector, use sector-specific series:

- Manufacturing: MANEMP (employment), IPMAN (production), DGORDER (orders), AWHMAN (hours)
- Construction: USCONS (employment), HOUST (starts), PERMIT (permits)
- Retail: USTRADE (employment), RSXFS (sales)
- Restaurants/Food service: CES7072200001 (employment)
- Healthcare: CES6562000001 (hospitals), CES6561000001 (ambulatory)
- Tech/Information: USINFO (employment)
- Finance: USFIRE (employment)
- Government: USGOVT (total), CES9091000001 (federal), CES9092000001 (state/local)
- Leisure & Hospitality: USLAH (employment)
- Transportation: USTPU (employment)
- Energy: CES1021100001 (mining), DCOILWTICO (oil price)
"""

# =============================================================================
# ECONOMIC REASONING THRESHOLDS
# =============================================================================

ECONOMIC_THRESHOLDS = """
## Economic Benchmarks for Interpretation

These help the LLM interpret whether values are good, bad, or neutral:

### Unemployment Rate (UNRATE)
- Below 3.5%: Very tight labor market, potential wage-price pressure
- 3.5% - 4.5%: Healthy / near full employment
- 4.5% - 6.0%: Elevated, labor market slack
- Above 6.0%: Significant weakness, likely recession

### Core Inflation (YoY)
- Below 1.5%: Disinflation risk, may need stimulus
- 1.5% - 2.5%: Near Fed's 2% target, healthy
- 2.5% - 3.5%: Elevated but making progress if falling
- 3.5% - 5.0%: Hot, Fed likely restrictive
- Above 5.0%: Crisis-level, aggressive Fed response

### GDP Growth (quarterly annualized)
- Below 0%: Contraction, possible recession
- 0% - 1.5%: Below trend, sluggish
- 1.5% - 2.5%: Trend growth (~2% long-run)
- 2.5% - 4.0%: Above trend, strong
- Above 4.0%: Boom, possibly unsustainable

### Fed Funds Rate
- 0% - 0.25%: Zero lower bound, maximum stimulus
- 0.25% - 2.5%: Accommodative
- 2.5% - 3.5%: Near neutral (r*)
- 3.5% - 5.0%: Restrictive
- Above 5.0%: Very restrictive

### Yield Curve (T10Y2Y)
- Below -0.5%: Deeply inverted, strong recession signal
- -0.5% to 0%: Inverted, watch closely
- 0% to 1.0%: Flat to normal
- Above 1.0%: Steep, economy expected to grow
"""

# =============================================================================
# ANTI-PATTERNS
# =============================================================================

ANTI_PATTERNS = """
## Things to NEVER Do

1. NEVER show U-6 when someone asks about "unemployment" - use U-3 (UNRATE or state UR)
2. NEVER show raw CPI index value (326.03) - show YoY % change (3.0%)
3. NEVER say "rising 9.1%" for a rate that went from 7.7% to 8.4% - say "up 0.7pp"
4. NEVER show total payroll level (159.5M) as the headline - show monthly change (+175K)
5. NEVER return generic national data for demographic queries (Black, Hispanic, Women)
6. NEVER return generic national data for state queries (use {STATE}UR not UNRATE)
7. NEVER show only 1 series when 3-4 would give a complete picture
8. NEVER use "basis points" - say "percentage points" or "pp"
9. NEVER explain what an acronym stands for in the summary (nobody cares what JOLTS stands for)
10. NEVER return interest rate data for rent/housing price queries ("increasing" ≠ "easing")
"""


def get_full_knowledge_prompt() -> str:
    """
    Get the complete economic knowledge base as a single string
    for inclusion in any LLM prompt.
    """
    return "\n\n".join([
        QUERY_INTENT_RULES,
        DISPLAY_RULES,
        STATE_SERIES_PATTERNS,
        DEMOGRAPHIC_SERIES_KNOWLEDGE,
        SECTOR_SERIES_KNOWLEDGE,
        ECONOMIC_THRESHOLDS,
        ANTI_PATTERNS,
    ])


def get_series_catalog_text() -> str:
    """
    Get a formatted text catalog of all available series organized by topic.
    This is what the LLM sees when deciding what data to fetch.
    """
    lines = []
    for topic, data in SERIES_BY_TOPIC.items():
        lines.append(f"\n### {data['description']}")
        for s in data.get('primary', []):
            lines.append(f"  * {s['id']}: {s['name']} - {s['use_for']}")
        for s in data.get('secondary', []):
            lines.append(f"    {s['id']}: {s['name']} - {s['use_for']}")
    return "\n".join(lines)


def get_compact_knowledge_prompt() -> str:
    """
    Get a shorter version of the knowledge base for token-limited contexts.
    Includes only the most critical rules.
    """
    return "\n\n".join([
        QUERY_INTENT_RULES,
        DISPLAY_RULES,
        ANTI_PATTERNS,
    ])
