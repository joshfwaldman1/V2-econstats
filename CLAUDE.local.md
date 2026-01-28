# EconStats Project Memory

## Critical Rules (User-Specified)
- **MAKE NO MISTAKES** - Be thorough. Test edge cases. Think about how users actually type queries.
- **DO NOT HALLUCINATE DATES** - Never make up or guess date ranges
- **PAYROLLS = CHANGES NOT LEVELS** - When using payroll data, focus on month-over-month or year-over-year changes, not absolute employment levels

## Comparison Query Detection (query_router.py)
**Comparison keywords must be exhaustive:**
- "vs", "versus", "compared to", "compare", "than", "against", "relative to", "between", "and"

**Region aliases must cover all common spellings:**
- US: "us", "usa", "u.s.", "u.s", "america", "american", "united states"
- Eurozone: "eurozone", "euro area", "euro zone", "eu", "europe", "european"

**When a user asks X vs Y, ALWAYS return data for BOTH X and Y.**

## Economic Comparison Fundamentals (CRITICAL)
**NEVER compare apples to oranges. All comparisons must be equivalent:**

| Dimension | Rule | Example Violation |
|-----------|------|-------------------|
| **YoY vs QoQ** | NEVER mix year-over-year with quarter-over-quarter | US GDP 2.3% YoY vs Eurozone 0.6% QoQ = WRONG |
| **Real vs Nominal** | ALWAYS compare real with real (inflation-adjusted) | Real GDP vs Nominal GDP = WRONG |
| **Same periodicity** | Match monthly/quarterly/annual data appropriately | Annual IMF data vs Monthly FRED = Be careful |

**Series metadata in `dbnomics.py` and `query_router.py`:**
- `measure_type`: "real", "nominal", "rate", "index"
- `change_type`: "yoy", "qoq", "mom", "level"
- `transform`: What to apply to raw FRED data (e.g., "yoy_pct")

**FRED series that need transformation:**
- GDPC1 (Real GDP): Level → must calculate YoY % change
- CPIAUCSL (CPI): Index → must calculate YoY % change
- UNRATE, FEDFUNDS: Already rates, display as-is

## GDP Display Rules
**Show both YoY and quarterly - YoY is primary (smoother), quarterly is secondary (timely):**

| Series | Name | Use |
|--------|------|-----|
| **A191RO1Q156NBEA** | GDP YoY growth | Primary - smoother trend, less noise |
| **A191RL1Q225SBEA** | GDP quarterly annualized | Secondary - the "2.8% in Q3" headline number |

Both should be shown on GDP charts. YoY gives the trend; quarterly gives the latest reading.

## GDP Nowcasts (SUPPLEMENTARY ONLY)
**Nowcasts are less valuable than established forecasts. Use sparingly.**

| Series | Source | Description | Issues |
|--------|--------|-------------|--------|
| **GDPNOW** | Atlanta Fed | Real-time GDP nowcast | Volatile (1-2pp swings common). Often misleading early in quarter. |
| **STLENI** | St. Louis Fed | Alternative nowcast | Often diverges wildly from GDPNow. |

**Rules for nowcasts:**
- **DO NOT include in main series lists** - Official GDP (A191RL1Q225SBEA) is the primary measure
- **Cite at bottom only** - If mentioned, add as supplementary note: "*For real-time estimates, see GDPNow/STLENI - but note these are volatile and often diverge.*"
- **Only show for explicit nowcast queries** - "gdpnow", "nowcast" queries can return these series directly
- **NY Fed Nowcast** - Also available at newyorkfed.org/research/policy/nowcast (not in FRED)

## LLM Integration Patterns
- **LLMs hallucinate series IDs** - Never have LLMs generate FRED series IDs directly
- **Use topic discovery instead** - Have LLMs suggest dimensions/topics, then use FRED API to find valid series
- **Validate all series** - Use `validate_series_relevance()` to filter irrelevant/overly broad series
- **Claude API auth issues** - May get 401 errors; Gemini works as fallback in ensemble

## Architecture
- **Economist Reasoning (PRIMARY)**: `core/economist_reasoning.py` - AI reasons about what indicators an economist would need, then searches FRED
- **RAG Catalog**: 115+ curated FRED series in `agents/series_rag.py` with semantic search
- **Pre-computed Plans**: 460+ query-to-series mappings across `agents/plans_*.json` files (fast-path backstop)
- **Hybrid Fallback**: Combine RAG + FRED API search when reasoning fails

## Query Processing Flow (UPDATED - "Thinking First")
1. **Query Understanding** (NEW) - Gemini deeply analyzes query intent BEFORE any routing
2. **Pre-computed plan check** - Exact match only (fast path for known queries)
3. **Comparison Router** - Enhanced by query understanding for US vs X queries
4. **Economist Reasoning** (PRIMARY) - AI thinks: "To answer this, an economist would need X, Y, Z..."
5. **FRED Search** - Search for each concept the AI identified
6. **Relevance Filter** - Skip series that don't match the intended concept
7. **Demographic Filter** - Use query understanding to filter wrong demographic data
8. **Fallback** - If reasoning fails, use hybrid RAG + FRED search

The key insight: We now "think first" about what the query REALLY means before routing.
This prevents issues like returning women's data for Black workers queries.

## Query Understanding ("Thinking First" Layer)
**Module**: `agents/query_understanding.py`

Uses Gemini to deeply analyze queries BEFORE any routing:
- **Intent**: What is the user really asking? (factual, analytical, comparison, forecast, causal)
- **Entities**: Demographics, regions, sectors, time periods mentioned
- **Routing**: Which data sources to use (FRED, DBnomics, Zillow, EIA, etc.)
- **Pitfalls**: What mistakes to avoid (e.g., "Don't use overall unemployment for Black workers")

**Key Functions**:
- `understand_query(query)` - Returns structured understanding
- `get_routing_recommendation(understanding)` - Returns routing decisions

**Example Output** for "How are Black workers doing?":
```python
{
    "intent": {"query_type": "analytical"},
    "entities": {"demographics": ["black"], "regions": ["us"]},
    "routing": {"is_demographic_specific": True, "primary_source": "fred"},
    "pitfalls": ["Do NOT use overall unemployment rate (UNRATE)"]
}
```

## Demographic Routing (CRITICAL)
The `extract_demographic_group()` function prevents cross-demographic confusion:
- "Black workers" → ONLY matches Black-specific plans (not women's data!)
- Demographic keywords: black, hispanic, latino, women, men, immigrant, youth, older

## Geographic Handling
The `detect_geographic_scope()` function detects state/regional queries:
- **Searches FRED** for state-specific series (e.g., TXUR, TXNA for Texas)
- Falls back to national data with warning if no state series found
- State series examples: {STATE}UR (unemployment), {STATE}NA (nonfarm payrolls), {STATE}RGSP (GDP)

## Temporal Query Handling (NEW)
The `extract_temporal_filter()` function handles time references in queries:
- **Specific years**: "inflation in 2022" → filters to 2022 data
- **Relative**: "last year", "this year", "past 3 years"
- **Periods**: "pre-covid" (through Feb 2020), "during covid" (Mar 2020 - Dec 2021), "post-covid" (2022+)
- **Recessions**: "great recession", "2008 crisis" → Dec 2007 - Jun 2009

## Presentation Validation (Stock vs Flow vs Rate)
The `validate_presentation()` function uses AI to determine how each series should be displayed:

| Category | Example | Display |
|----------|---------|---------|
| **STOCK** | Total Payrolls (159M) | Show as monthly CHANGE (+256K) |
| **FLOW** | Initial Claims (200K/week) | Show as LEVEL (already per-period) |
| **RATE** | Unemployment (4.4%) | Show as LEVEL (already a ratio) |

Key insight: Stocks are cumulative totals where the level is less meaningful than the change. Flows are already measured per-period, so the level IS meaningful.

## Synonym Handling
The `apply_synonyms()` function normalizes query terms using **word-boundary matching** to avoid substring corruption:
- Uses regex `\b...\b` to match whole words only
- Prevents "pay" → "wages" from corrupting "payrolls" → "wagesrolls"
- Sorts synonyms by length (longest first) for multi-word phrases

## Coverage Expansion (NEW)
Added series and plans for:
- **Small business**: BUSLOANS, DRTSCLCC (lending standards), NFIBOPTIMISM
- **Supply chain**: NAPMPMD (supplier deliveries), TSIFRGHT (freight), RAILFRTINTERMODAL
- **Industry sectors**: MANEMP, USCONS, USHCS, USLAH, USINFO, USTRADE, USGOVT
- **Veterans**: LNS14049526 (post-9/11 veteran unemployment)
- **Auto/vehicles**: TOTALSA, ALTSALES
- **Energy**: IPG211111CS (oil production), DCOILWTICO
- **Money supply**: M2SL, WALCL (Fed balance sheet)

## Polymarket Integration (Forward-Looking Data)
- `agents/polymarket.py` - Fetches prediction market data for forward-looking sentiment
- **Tracked markets**: recession odds, Fed rate expectations, GDP forecasts, tariff revenue
- **Display**: Shows relevant predictions below summary when query matches keywords
- **Keywords matched**: recession, fed, gdp, growth, economy, tariff, inflation, interest rate
- **Caching**: 15-minute TTL to avoid API spam
- **API**: Uses Polymarket Gamma API (https://gamma-api.polymarket.com)

## Recession Scorecard (Recession Dashboard)
- `agents/recession_scorecard.py` - Comprehensive recession risk dashboard
- **Purpose**: Go-to tool for "is a recession coming?" questions
- **Indicators tracked**:
  - `SAHMREALTIME` - Sahm Rule (triggered at 0.5 when 3-mo unemployment rises above 12-mo low)
  - `T10Y2Y` - Yield curve spread (inverted = warning, has preceded every recession since 1970)
  - `UMCSENT` - Consumer sentiment (sharp drops precede recessions)
  - `ICSA` - Initial jobless claims 4-week average (rising = warning)
  - Polymarket recession odds (forward-looking market sentiment)
- **Status colors**: Green (normal), Yellow (caution), Red (warning)
- **Overall risk levels**: LOW, MODERATE, ELEVATED, HIGH
- **Display**: Prominent dashboard box at top of response for recession queries
- **Queries handled**: "recession", "is a recession coming", "recession odds", "sahm rule", "yield curve inversion", "hard landing", "soft landing"

## Fed SEP Integration (FOMC Projections & Guidance) - ENHANCED
- `agents/fed_sep.py` - Fetches Summary of Economic Projections and provides Fed guidance
- **No API key required** - Scrapes Fed's public HTML tables

### What Fed Guidance Shows:
1. **Current Fed funds rate** - Target range and last change info
2. **FOMC's projected path** - From the dot plot (rate path through 2027)
3. **Key quotes from FOMC statements** - Recent statement highlights
4. **Tone indicator** - Hawkish/dovish relative to expectations

### Variables Tracked:
  - `sep_gdp` - Real GDP growth projections
  - `sep_unemployment` - Unemployment rate projections
  - `sep_pce_inflation` - PCE inflation projections
  - `sep_core_pce` - Core PCE inflation projections
  - `sep_fed_funds` - Federal funds rate projections (dot plot)

### Keywords That Trigger Fed Guidance (EXPANDED):
**Core Fed terms**: "fed", "fomc", "federal reserve", "powell"
**Rate actions**: "rate cut", "rate hike", "cutting rates", "raising rates"
**Policy terms**: "monetary policy", "tightening", "easing", "hawkish", "dovish", "pivot"
**Forward guidance**: "dot plot", "rate path", "terminal rate", "neutral rate"

### Key Functions:
- `is_fed_related_query(query)` - Broad check for any Fed-related query
- `is_sep_query(query)` - Specific check for SEP/projection queries
- `get_fed_guidance_for_query(query)` - Returns full Fed guidance (rate + projections + FOMC summary)
- `get_current_fed_funds_rate()` - Current target range and last change
- `get_recent_fomc_summary()` - Key quotes and highlights from recent meetings

### FOMC Statement Summaries:
Hardcoded summaries for recent FOMC meetings (December 2024, November 2024, September 2024) including:
- Rate decision (e.g., "Cut 25 bps to 4.25-4.50%")
- Key quote from statement
- Highlights (3-4 bullet points)
- Tone (hawkish/dovish/neutral)

### Display:
- Blue callout box below summary with Fed guidance
- Shows current rate, dot plot path, and key takeaways
- Includes source URL to Fed website

### Update Frequency:
- Quarterly (March, June, September, December FOMC meetings)
- **Maintainer Note**: Update `CURRENT_FED_FUNDS_RATE` and `FOMC_STATEMENT_SUMMARIES` after each FOMC meeting

### Fallback:
- Hardcoded December 2024 data if scraping fails

## Stock Market Integration
- `agents/stocks.py` - Query plans for stock market data (uses FRED, not external APIs)
- **Series**: SP500, DJIA, NASDAQCOM, VIXCLS, T10Y2Y, BAMLH0A0HYM2, GOLDAMGBD228NLBM, DCOILWTICO
- **Queries handled**: "stock market", "s&p 500", "dow jones", "nasdaq", "vix", "yield curve", "gold price", "oil price"
- **Integration**: Falls back to stock plans if no precomputed economic plan matches

## Zillow Integration (Market Rents & Home Values)
- `agents/zillow.py` - Fetches actual market rents and home values from Zillow Research
- **No API key required** - Uses free public CSV downloads
- **Series**:
  - `zillow_zori_national` - Zillow Observed Rent Index (actual market rents)
  - `zillow_zhvi_national` - Zillow Home Value Index
  - `zillow_rent_yoy` - Rent growth year-over-year
  - `zillow_home_value_yoy` - Home value growth year-over-year
- **Queries handled**: "zillow rent", "market rent", "actual rents", "zhvi", "zori"
- **Better than FRED for**: Real-time rent data (CPI rent lags by months)

## EIA Integration (Energy Data)
- `agents/eia.py` - Detailed energy data from US Energy Information Administration
- **Requires**: `EIA_API_KEY` env var (free at https://www.eia.gov/opendata/register.php)
- **Series**:
  - `eia_wti_crude` - WTI crude oil spot price
  - `eia_brent_crude` - Brent crude oil price
  - `eia_gasoline_retail` - Retail gasoline prices
  - `eia_diesel_retail` - Diesel fuel prices
  - `eia_natural_gas_henry_hub` - Henry Hub natural gas
  - `eia_crude_stocks` - US crude oil inventories
  - `eia_crude_production` - US oil production
  - `eia_electricity_residential` - Residential electricity prices
- **Better than FRED for**: More granular energy data, weekly updates

## Alpha Vantage Integration (Real-Time Markets)
- `agents/alphavantage.py` - Daily market data for stocks, forex, commodities
- **Requires**: `ALPHAVANTAGE_API_KEY` env var (free at https://www.alphavantage.co/support/#api-key)
- **Series**:
  - Stocks: `av_spy`, `av_qqq`, `av_dia`, `av_iwm` (ETFs tracking indices)
  - Treasuries: `av_treasury_10y`, `av_treasury_2y`, `av_treasury_30y`, `av_treasury_3m`
  - Forex: `av_eurusd`, `av_usdjpy`, `av_gbpusd`, `av_dollar_index`
  - Commodities: `av_crude_oil`, `av_brent`, `av_natural_gas`
  - Economic: `av_real_gdp`, `av_cpi`, `av_unemployment`, `av_fed_funds`
- **Better than FRED for**: Daily data (FRED indices are delayed), forex rates

## DBnomics Integration (International Data)
- `agents/dbnomics.py` - International economic data from IMF, Eurostat, ECB, BOE
- **API**: https://api.db.nomics.world/v22/
- **Coverage**:
  - Eurozone: GDP, inflation (HICP), unemployment
  - UK: GDP, CPI, Bank of England rate
  - Japan: GDP, inflation (IMF)
  - China: GDP, inflation (IMF)
  - Germany: GDP, unemployment
  - Canada, Mexico, India, Brazil: GDP (IMF)
  - ECB main refinancing rate
- **Queries handled**: "eurozone economy", "how is china doing", "uk inflation", "ecb rate"
- **Data format**: Converted to FRED-compatible (dates, values, info) for seamless integration

## Premium Economist Analysis (Deep Insights)
- `core/economist_analysis.py` - Generates economist-quality analysis connecting multiple indicators
- **Purpose**: This is what differentiates EconStats from raw data tools - we explain what data means

### What It Does:
1. **Connects indicators**: Links unemployment, inflation, GDP into coherent narrative
2. **Applies economic reasoning**: Uses encoded rules about economic relationships
3. **Highlights risks/opportunities**: Forward-looking assessment
4. **Confidence scoring**: Rates analysis as high/medium/low confidence

### Output Structure:
- **Headline**: One-sentence answer to the user's question
- **Narrative**: 3-5 bullets connecting the dots between indicators
- **Key Insight**: The single most important takeaway
- **Risks**: What could go wrong (2-3 items)
- **Opportunities**: What could go right (2-3 items)
- **Watch Items**: What to monitor going forward

### Example Output:
For "How is the economy doing?" with unemployment 4.1%, payrolls +200K, GDP 2.5%, inflation 3.2%:
> "The labor market remains solid with unemployment at 4.1% and strong job gains of 200K. However, inflation at 3.2% remains above the Fed's 2% target, suggesting monetary policy will stay restrictive. GDP growth of 2.5% indicates resilient expansion despite higher rates. Key watch: whether labor market strength can persist as restrictive policy continues."

### Economic Reasoning Rules:
Encodes relationships like:
- `labor_tight`: unemployment < 4.5% AND job_openings_per_unemployed > 1.0 → "wage pressures likely to persist"
- `inflation_progress`: 2.5 < core_inflation <= 3.5 AND falling → "rate cuts becoming more likely"
- `goldilocks`: low unemployment + low inflation + positive growth → "conditions support continued expansion"
- `stagflation_risk`: rising unemployment + elevated inflation → "Fed faces difficult tradeoffs"

### Display:
- Yellow gradient callout box with gold border
- Confidence badge (green/yellow/red)
- Two-column layout for risks/opportunities
- Shown after historical context, before charts

## Smart Query Router (Comparison Queries)
- `agents/query_router.py` - Handles multi-source queries
- **Comparison detection**: "vs", "compared to", "compare", multiple regions mentioned
- **Two types of comparisons**:

### 1. Domestic Comparisons (FRED-only)
Compares two US indicators on the same chart. All data from FRED.
- **Example queries**:
  - "Black unemployment vs overall" → LNS14000006 + UNRATE
  - "inflation vs wage growth" → CPIAUCSL + CES0500000003
  - "Job openings vs unemployed" → JTSJOL + LNS13000000
  - "Core vs headline inflation" → CPILFESL + CPIAUCSL
  - "2 year vs 10 year treasury" → DGS2 + DGS10
  - "housing starts vs permits" → HOUST + PERMIT
- **Automatic combine_chart=True** for all domestic comparisons
- **Pattern matching**: ~25 curated comparison patterns in DOMESTIC_COMPARISONS dict

### 2. International Comparisons (FRED + DBnomics)
Compares US to other countries. Data from FRED (US) + DBnomics (international).
- **Region extraction**: US, Eurozone, UK, Japan, China, Germany, Canada, Mexico, India, Brazil
- **Indicator extraction**: GDP/growth, inflation/CPI, unemployment, rates
- **Example queries**:
  - "US vs Eurozone GDP" → FRED:GDPC1 + DBnomics:eurozone_gdp
  - "Compare US and China growth" → FRED:GDPC1 + DBnomics:china_gdp
  - "UK inflation vs US" → FRED:CPIAUCSL + DBnomics:uk_inflation

## Key Files
- `app.py` - Main Streamlit app with query routing, temporal handling, geographic search
- `agents/query_understanding.py` - "Thinking First" layer - deep query analysis with Gemini
- `agents/agent_ensemble.py` - LLM ensemble for dimension discovery and validation
- `agents/series_rag.py` - RAG system with 115+ curated series
- `agents/polymarket.py` - Polymarket prediction market integration
- `agents/zillow.py` - Zillow housing data (no API key needed)
- `agents/eia.py` - EIA energy data (requires EIA_API_KEY)
- `agents/alphavantage.py` - Alpha Vantage market data (requires ALPHAVANTAGE_API_KEY)
- `core/economist_analysis.py` - Premium economist analysis with deep insights, risks, and opportunities
- `agents/plans_*.json` - Pre-computed query plans by category:
  - `plans_employment.json` - Jobs, sectors, demographics
  - `plans_economy_overview.json` - Economy, small business, supply chain
  - `plans_demographics.json` - Race/ethnicity, gender, immigrants
  - `plans_gdp.json` - GDP, growth, production
  - `plans_inflation.json` - CPI, PCE, shelter, food, energy
  - `plans_housing.json` - Prices, starts, permits, mortgage
  - `plans_fed_rates.json` - Fed funds, treasuries, yields
  - `plans_consumer.json` - Sentiment, spending, retail
  - `plans_trade_markets.json` - Trade, stocks, commodities

## Chart Design Principles (The Economist Style)
1. **Minimal but Informative** - Use simple charts (line, bar, scatter). Complex issues need simple visuals.
2. **Purpose-Driven** - Each chart answers ONE question. Ask "What insight do readers take away?"
3. **Clear Hierarchy** - Title (attention), subtitle (context/what we see), source (grayed out)
4. **Annotations** - Mark key events/turning points. Explain "why", not just "what"
5. **Restraint** - Show less to communicate more. Use color purposefully, not decoratively.
6. **Small Multiples** - Break complex comparisons into related smaller charts

## Recent Fixes (January 2026)
1. **Greedy synonym replacement** - Fixed substring corruption using word boundaries
2. **GDPC1 presentation** - Now shows YoY growth, not raw $28T level
3. **YoY calculation** - Fixed to handle quarterly data (4 obs/year), not just monthly
4. **Validation bypass** - Pre-computed plans now always validated
5. **Temporal queries** - Added extraction for year/period references
6. **Holistic patterns** - Expanded to catch "what about", "compare", industry queries
7. **Polymarket integration** - Added forward-looking prediction market data (recession, Fed, GDP)
8. **Eurozone GDP YoY fix** - Changed from QoQ (CLV_PCH_PRE) to YoY (CLV_PCH_SM) for proper US comparison
9. **Comparison metadata** - Added measure_type/change_type to all DBnomics and FRED comparison series
10. **Query Understanding layer** - NEW "Thinking First" approach using Gemini to deeply analyze query intent before routing. Prevents wrong demographic data (e.g., women's data for Black workers queries). See `agents/query_understanding.py`.
11. **Recession Scorecard** - NEW comprehensive "Recession Dashboard" for recession-related queries. Shows Sahm Rule, yield curve, consumer sentiment, initial claims, and Polymarket odds with color-coded status indicators. See `agents/recession_scorecard.py`.
12. **Premium Economist Analysis** - NEW deep analysis feature that connects multiple indicators into coherent narratives, applies economic reasoning, and highlights risks/opportunities. Displays as a yellow callout box with headline, narrative bullets, key insight, risks, and opportunities. See `core/economist_analysis.py`.
13. **Dynamic Series Selection** - NEW "on your feet" capability using Gemini to reason about unexpected queries. When no pre-computed plan exists, Gemini looks at available data catalog and selects appropriate series. Handles novel queries like "how are oil companies doing?" See `get_dynamic_series()` in `agents/query_understanding.py`.
14. **Mag7/Stock Routing Fix** - Stock market queries now route to Alpha Vantage daily data instead of lagged FRED monthly data. Added av_aapl, av_msft, av_googl, av_amzn, av_nvda, av_meta, av_tsla to alphavantage.py catalog.
15. **Sector ETF Mapping** - Sector-focused queries now correctly distinguish between stock queries vs employment queries. "Healthcare stocks" → av_xlv (ETF), "Healthcare sector" → USHEALTHEMPL (employment).
16. **Bubble/Valuation Judgment Layer** - Queries like "are we in an AI bubble?" now trigger Gemini web search for expert commentary. Added bubble-related patterns to JUDGMENT_PATTERNS in `agents/judgment_layer.py`.

## Validation Layer Pattern (CRITICAL)
**Module**: `agents/query_understanding.py` - `validate_series_for_query()`

The validation layer is a "gut check" that runs AFTER routing to ensure proposed series actually match query intent:

1. **Demographics** - If query mentions "Black workers" but routing returned UNRATE, override to LNS14000006
2. **Sectors** - If query mentions "manufacturing" but got generic PAYEMS, override to MANEMP
3. **Stock vs Employment** - If query says "healthcare stocks" but got USHEALTHEMPL, override to av_xlv
4. **Topics** - "oil companies" → av_xle + av_crude_oil (not generic employment)

**Order of checks**:
1. Demographics (highest priority - people get this wrong most)
2. Sectors (stock-focused vs employment-focused)
3. Stock/market queries
4. Topic-specific (bubble, bonds, emerging markets)

## Industry/Sector Query Routing
**Key insight**: Distinguish "X stocks" from "X sector":

| Query Pattern | Series Type | Examples |
|---------------|-------------|----------|
| "healthcare stocks" | Sector ETF | av_xlv |
| "healthcare sector" | Employment | USHEALTHEMPL |
| "oil companies" | Energy ETF + prices | av_xle, av_crude_oil |
| "energy sector" | Employment + prices | CES1021100001, DCOILWTICO |
| "tech companies" | Tech ETF | av_xlk, av_qqq |
| "tech employment" | Employment | USINFO |

**Implementation**: `SECTOR_TO_ETF` mapping in validate_series_for_query() uses stock-focused keywords to route appropriately.

## Judgment Layer for Expert Research
**Module**: `agents/judgment_layer.py`

Triggers Gemini web search for queries requiring interpretation/expert opinion:

**New patterns added for bubble/valuation questions**:
- `\b(bubble|overvalued|undervalued|overheated|frothy)\b`
- `\b(sustainable|unsustainable)\b`
- `\b(justified|warranted)\b`
- `\b(p/e|pe ratio|valuation)\b`
- `\b(crash|correction)\b.*(coming|imminent|likely)`

**Specialized search prompts**:
- Bubble questions get expanded prompt asking for P/E ratios, historical comparisons, bull/bear cases
- Standard economic questions get expert opinions on indicator levels

## P/E Ratio Data (NEW)
**Solution**: Alpha Vantage OVERVIEW endpoint provides fundamentals!

**New functions in `agents/alphavantage.py`**:
```python
get_company_fundamentals(symbol) -> dict
# Returns: pe_ratio, forward_pe, peg_ratio, price_to_book, price_to_sales,
#          eps, market_cap, beta, 52_week_high/low, profit_margin, etc.

get_market_pe_summary() -> dict
# Returns P/E ratios for SPY, QQQ, and Mag7 stocks with average
```

**Free tier limits**: 25 requests/day (Alpha Vantage OVERVIEW)

**Use for**: Bubble/valuation questions - "are we in an AI bubble?", "is the market overvalued?"

**Alternative free APIs for fundamentals**:
- Financial Modeling Prep: 250 calls/day
- Finnhub: 60 calls/min
- EODHD: Limited free tier with 30+ years history

## Shiller CAPE Ratio Integration (NEW)
**Module**: `agents/shiller.py`
**Data Source**: Robert Shiller's "Irrational Exuberance" dataset (Yale University)
**File**: `data/shiller_pe.xls` (downloaded from Shiller's website)

The Shiller CAPE (Cyclically Adjusted P/E) is the gold standard for long-term market valuation:
- S&P 500 price divided by 10-year average of inflation-adjusted earnings
- Data from 1881 to present (143+ years of history)
- Updated monthly

**Key Functions**:
```python
get_cape_series() -> dict
# Returns dates, values, info in standard FRED format for charting

get_current_cape() -> dict
# Returns: current_value, percentile, vs_average, historical_range, comparisons, interpretation

get_bubble_comparison_data() -> dict
# Returns: current CAPE vs dot-com peak, streak analysis, summary

is_valuation_query(query) -> bool
# Detects bubble/valuation keywords
```

**Historical Benchmarks**:
- Long-term average: 17.0
- Dot-com peak (Dec 1999): 44.2
- 2008 crisis low: 13.3
- Current (Jan 2026): ~40 (98th percentile)

**Queries that trigger CAPE display**:
- "are we in a bubble?"
- "is the market overvalued?"
- "cape ratio"
- "shiller pe"
- "market valuation"

**Display**: Blue gradient box showing current CAPE, percentile, vs average, vs dot-com, plus 30-year historical chart
