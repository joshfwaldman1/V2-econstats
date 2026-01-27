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
    # Short description explaining what this indicator measures (for metric cards)
    short_description: Optional[str] = None


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
        short_description='Total U.S. jobs excluding farms. Released monthly (first Friday). Change shown is month-over-month. Adding 150K+ jobs/month is strong; 50-75K keeps pace with population growth; negative means job losses.',
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
        short_description='Share of people actively job-seeking who can\'t find work. <4% is historically tight; doesn\'t count those who\'ve stopped looking.',
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
        short_description='Quarterly growth rate of total economic output (annualized)',
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
        short_description='Prices of a fixed basket of goods/services. Released monthly. Shown as year-over-year % change. The Fed targets about 2% per year.',
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
        short_description='CPI excluding food and energy (which swing month-to-month). Released monthly, shown year-over-year. Reveals underlying inflation trend.',
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
        short_description='The interest rate banks charge each other for overnight loans. Set by the Federal Reserve. When the Fed raises this rate, all borrowing gets more expensive, which slows growth and (eventually) inflation.',
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
        short_description='Long-term borrowing cost benchmark; drives mortgage and corporate bond rates',
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
        short_description='Short-term rate reflecting market expectations for Fed policy',
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
        short_description='Average 30-year fixed mortgage rate. Each 1% rise cuts buying power ~10%. Below 4% is historically cheap; above 7% chills the market.',
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
        short_description='The 10-year Treasury interest rate minus the 2-year rate. Normally positive (longer loans cost more). When negative ("inverted"), it means bond markets expect the Fed to cut rates because the economy is slowing. Preceded every recession since 1970—but the 2022-24 inversion was a false alarm.',
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
        short_description='Gap between current 3-mo avg unemployment and its 12-mo low. At 0.5+, recession has likely begun. Called every recession since 1970.',
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
        short_description='New unemployment filings each week—most timely labor indicator. <250K = healthy, >300K = trouble brewing.',
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
        short_description='% of adults working or looking for work',
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
        short_description='% of 25-54 year-olds with jobs. Avoids retiree/student distortions—many economists\' favorite labor gauge. ~80% is a strong reading.',
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
        short_description='The Fed\'s official 2% inflation target. Released monthly, shown year-over-year. Excludes food/energy. Broader than CPI because it adjusts when consumers switch to cheaper alternatives.',
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
        short_description='Fed\'s official inflation gauge; broader than CPI',
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
        short_description='Monthly survey asking consumers about their finances and economic expectations. >90 = optimistic, <70 = pessimistic. Can predict spending shifts.',
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
        short_description='Consumer spending at stores—drives ~70% of economic growth',
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
        short_description='% of income saved; below 4% suggests stretched consumers',
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
        short_description='Real-time GDP estimate updated daily; most current read on economic momentum',
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
        short_description='Home prices across 20 major metro areas',
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
        short_description='New home construction; leading indicator of housing supply',
        bullets=[
            'New residential construction starts—a leading indicator of housing supply and economic activity.',
            'Sensitive to mortgage rates and builder confidence.'
        ]
    ),
    # ==========================================================================
    # GDP VARIANTS - Very important to distinguish quarterly vs annual
    # ==========================================================================
    'A191RL1Q225SBEA': SeriesInfo(
        id='A191RL1Q225SBEA',
        name='Real GDP Growth Rate',
        unit='Percent',
        source='U.S. Bureau of Economic Analysis',
        data_type='growth_rate',
        frequency='quarterly',
        short_description='How fast the economy grew this quarter vs last quarter, projected to a full year. Released quarterly. 2-3% is healthy; two negative quarters in a row is often called a recession.',
        bullets=[
            'Quarterly GDP growth expressed at an annualized rate—the standard way GDP is reported in the U.S.',
            'Shows quarter-to-quarter momentum. Growth above 2% is healthy; negative readings for 2+ quarters suggest recession.'
        ]
    ),
    'PB0000031Q225SBEA': SeriesInfo(
        id='PB0000031Q225SBEA',
        name='Core GDP (Final Sales to Private Domestic Purchasers)',
        unit='Percent',
        source='U.S. Bureau of Economic Analysis',
        data_type='growth_rate',
        frequency='quarterly',
        short_description='GDP minus volatile trade/inventories; shows underlying private demand',
        bullets=[
            'Strips out volatile trade, inventories, and government spending—shows underlying private-sector demand.',
            'Economists often prefer this to headline GDP because it better reflects sustainable economic momentum.'
        ]
    ),
    'A191RL1A225NBEA': SeriesInfo(
        id='A191RL1A225NBEA',
        name='Real GDP Growth (Annual)',
        unit='Percent',
        source='U.S. Bureau of Economic Analysis',
        data_type='growth_rate',
        frequency='annual',
        short_description='Year-over-year economic growth; ~2% is typical, >3% is strong',
        bullets=[
            'Year-over-year GDP growth rate—smoother than quarterly data and better for long-term comparisons.',
            'Average U.S. growth has been ~2% since 2000. Growth above 3% is considered strong.'
        ]
    ),
    'GDPC1': SeriesInfo(
        id='GDPC1',
        name='Real GDP Level (Billions of 2017 Dollars)',
        unit='Billions of Chained 2017 Dollars',
        source='U.S. Bureau of Economic Analysis',
        data_type='level',
        frequency='quarterly',
        short_description='Total size of the U.S. economy in 2017 dollars',
        bullets=[
            'Total economic output in inflation-adjusted dollars—the size of the U.S. economy.',
            'Currently around $23 trillion. Used to compare economic size over time or across countries.'
        ]
    ),
    # ==========================================================================
    # ADDITIONAL EMPLOYMENT SERIES
    # ==========================================================================
    'JTSJOL': SeriesInfo(
        id='JTSJOL',
        name='Job Openings (JOLTS)',
        unit='Level in Thousands',
        source='U.S. Bureau of Labor Statistics',
        data_type='level',
        short_description='Unfilled positions; >7M signals tight labor market',
        bullets=[
            'Total job openings across the economy—a measure of labor demand and business confidence.',
            'Peaked at 12 million in 2022; levels above 7 million indicate a tight labor market.'
        ]
    ),
    'LNS11300060': SeriesInfo(
        id='LNS11300060',
        name='Prime-Age Labor Force Participation Rate',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        short_description='% of 25-54 year-olds working or looking for work. Strips out retirees and students for a cleaner read on worker engagement.',
        bullets=[
            'Share of Americans aged 25-54 in the labor force—avoids distortions from retirees and students.',
            'Has recovered to pre-pandemic levels, suggesting strong labor force attachment.'
        ]
    ),
    'LNS11300000': SeriesInfo(
        id='LNS11300000',
        name='Labor Force Participation Rate (All)',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        short_description='% of all adults (16+) working or job-seeking. Has fallen from 67% in 2000 as baby boomers retire.',
        bullets=[
            'Share of all adults (16+) either working or seeking work.',
            'Has declined from 67% in 2000 due to aging population and rising disability.'
        ]
    ),
    'MANEMP': SeriesInfo(
        id='MANEMP',
        name='Manufacturing Employment',
        unit='Thousands of Persons',
        source='U.S. Bureau of Labor Statistics',
        data_type='level',
        short_description='Factory jobs; down from 19M in 1979 to ~13M today',
        bullets=[
            'Total jobs in the manufacturing sector—a key indicator of industrial strength.',
            'Has declined from 19 million in 1979 to around 13 million today due to automation and offshoring.'
        ]
    ),
    'U6RATE': SeriesInfo(
        id='U6RATE',
        name='U-6 Unemployment Rate (Broad)',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        short_description='Broadest jobless measure; includes part-timers wanting full-time work',
        bullets=[
            'The broadest measure of unemployment—includes discouraged workers and involuntary part-time.',
            'Typically runs 3-4 percentage points higher than the headline U-3 rate.'
        ]
    ),
    # ==========================================================================
    # INFLATION COMPONENTS
    # ==========================================================================
    'CUSR0000SAH1': SeriesInfo(
        id='CUSR0000SAH1',
        name='CPI: Shelter',
        unit='Index',
        source='U.S. Bureau of Labor Statistics',
        data_type='index',
        show_yoy=True,
        yoy_name='Shelter Inflation Rate',
        yoy_unit='% Change YoY',
        short_description='Housing costs in CPI; ~1/3 of index; lags market rents by 6-12 months',
        bullets=[
            'The largest component of CPI—about 1/3 of the index. Includes rent and owners\' equivalent rent.',
            'Shelter inflation is "sticky" and lags actual market rents by 6-12 months.'
        ]
    ),
    'CUSR0000SEHA': SeriesInfo(
        id='CUSR0000SEHA',
        name='CPI: Rent of Primary Residence',
        unit='Index',
        source='U.S. Bureau of Labor Statistics',
        data_type='index',
        show_yoy=True,
        yoy_name='Rent Inflation Rate',
        yoy_unit='% Change YoY',
        short_description='What renters pay; key predictor of future shelter inflation',
        bullets=[
            'Measures changes in what tenants pay for rent—excludes homeowners.',
            'A key component for forecasting future shelter inflation trends.'
        ]
    ),
    # ==========================================================================
    # CONSUMER & RETAIL
    # ==========================================================================
    'RSXFS': SeriesInfo(
        id='RSXFS',
        name='Retail Sales (Ex. Food Services)',
        unit='Millions of Dollars',
        source='U.S. Census Bureau',
        data_type='level',
        show_yoy=True,
        short_description='Consumer spending at stores (excluding restaurants). Released monthly. Consumer spending is ~70% of GDP.',
        bullets=[
            'Retail sales excluding restaurants—shows goods spending by consumers.',
            'Consumer spending drives ~70% of GDP, making this a key economic indicator.'
        ]
    ),
    # ==========================================================================
    # MARKETS
    # ==========================================================================
    'SP500': SeriesInfo(
        id='SP500',
        name='S&P 500 Index',
        unit='Index',
        source='S&P Dow Jones Indices',
        data_type='index',
        sa=False,
        short_description='Benchmark U.S. stock index tracking 500 largest companies',
        bullets=[
            'The benchmark U.S. stock index—tracks 500 of the largest American companies.',
            'Widely considered the best single gauge of U.S. equity market performance.'
        ]
    ),
    'DCOILWTICO': SeriesInfo(
        id='DCOILWTICO',
        name='WTI Crude Oil Price',
        unit='Dollars per Barrel',
        source='U.S. Energy Information Administration',
        data_type='level',
        sa=False,
        short_description='West Texas Intermediate—the U.S. benchmark oil price. Directly affects gas prices and inflation.',
        bullets=[
            'West Texas Intermediate—the U.S. benchmark crude oil price.',
            'Oil prices affect gasoline costs, inflation, and energy sector profits.'
        ]
    ),
    'DCOILBRENTEU': SeriesInfo(
        id='DCOILBRENTEU',
        name='Brent Crude Oil Price',
        unit='Dollars per Barrel',
        source='U.S. Energy Information Administration',
        data_type='level',
        sa=False,
        short_description='Global benchmark oil price (from North Sea). Usually trades slightly above WTI.',
        bullets=[
            'Brent crude—the global benchmark oil price.',
            'Typically trades at a small premium to WTI due to global demand dynamics.'
        ]
    ),
    # ==========================================================================
    # WAGES
    # ==========================================================================
    'CES0500000003': SeriesInfo(
        id='CES0500000003',
        name='Average Hourly Earnings (Private)',
        unit='Dollars per Hour',
        source='U.S. Bureau of Labor Statistics',
        data_type='level',
        show_yoy=True,
        yoy_name='Wage Growth Rate',
        yoy_unit='% Change YoY',
        short_description='Average hourly pay; growth >4% may fuel inflation',
        bullets=[
            'Average hourly pay for private-sector workers—a key measure of wage growth.',
            'The Fed watches wage growth closely; sustained gains above 4% may pressure inflation.'
        ]
    ),
    # ==========================================================================
    # TRADE
    # ==========================================================================
    'BOPGSTB': SeriesInfo(
        id='BOPGSTB',
        name='Trade Balance (Goods & Services)',
        unit='Millions of Dollars',
        source='U.S. Bureau of Economic Analysis',
        data_type='level',
        short_description='Exports minus imports; negative = trade deficit',
        bullets=[
            'The difference between exports and imports—negative means trade deficit.',
            'The U.S. has run persistent deficits since the 1970s, recently around $60-80B/month.'
        ]
    ),
    'IMPGS': SeriesInfo(
        id='IMPGS',
        name='Imports of Goods & Services',
        unit='Billions of Dollars',
        source='U.S. Bureau of Economic Analysis',
        data_type='level',
        short_description='Value of goods/services bought from abroad. Rising imports often signal strong U.S. consumer demand.',
        bullets=[
            'Total value of goods and services imported into the U.S.',
            'Strong imports often reflect healthy consumer demand and a strong dollar.'
        ]
    ),
    'EXPGS': SeriesInfo(
        id='EXPGS',
        name='Exports of Goods & Services',
        unit='Billions of Dollars',
        source='U.S. Bureau of Economic Analysis',
        data_type='level',
        short_description='Value of goods/services sold abroad. Rises when global demand is strong or the dollar weakens.',
        bullets=[
            'Total value of goods and services exported from the U.S.',
            'Export growth is boosted by global demand and a weaker dollar.'
        ]
    ),
    'IMPCH': SeriesInfo(
        id='IMPCH',
        name='Imports from China',
        unit='Millions of Dollars',
        source='U.S. Census Bureau',
        data_type='level',
        short_description='Goods bought from China—historically our #1 import source. Share has dropped due to tariffs and supply chain reshoring.',
        bullets=[
            'Value of goods imported from China—our largest source of imports.',
            'Tariffs and supply chain shifts have reduced China\'s share in recent years.'
        ]
    ),
    'EXPCH': SeriesInfo(
        id='EXPCH',
        name='Exports to China',
        unit='Millions of Dollars',
        source='U.S. Census Bureau',
        data_type='level',
        short_description='Goods sold to China—mostly soybeans, aircraft, and chips. Volatile due to trade tensions.',
        bullets=[
            'Value of goods exported to China—primarily agricultural products and aircraft.',
            'Trade tensions have created significant volatility in this relationship.'
        ]
    ),
    # ==========================================================================
    # INTERNATIONAL (EUROZONE)
    # ==========================================================================
    'CLVMNACSCAB1GQEA19': SeriesInfo(
        id='CLVMNACSCAB1GQEA19',
        name='Eurozone Real GDP',
        unit='Millions of Chained 2015 Euros',
        source='Eurostat',
        data_type='level',
        frequency='quarterly',
        short_description='Total economic output of the 19 countries using the euro. Released quarterly. Useful for US-Europe comparisons.',
        bullets=[
            'Total economic output of the 19 Eurozone countries.',
            'Useful for comparing U.S. and European economic performance.'
        ]
    ),
    'LRHUTTTTEZM156S': SeriesInfo(
        id='LRHUTTTTEZM156S',
        name='Eurozone Unemployment Rate',
        unit='Percent',
        source='OECD',
        data_type='rate',
        short_description='Jobless rate across the 19 euro-area countries. Historically runs higher than U.S. due to stricter labor laws.',
        bullets=[
            'The unemployment rate across Eurozone countries.',
            'Historically higher than U.S. due to different labor market structures.'
        ]
    ),
    'EA19CPALTT01GYM': SeriesInfo(
        id='EA19CPALTT01GYM',
        name='Eurozone Inflation Rate',
        unit='Percent',
        source='OECD',
        data_type='growth_rate',
        short_description='Year-over-year price changes in the euro area. The European Central Bank targets 2%, like the Fed.',
        bullets=[
            'Year-over-year inflation in the Eurozone.',
            'The ECB targets 2% inflation, similar to the Fed.'
        ]
    ),
    # ==========================================================================
    # DEMOGRAPHICS - Employment by group
    # ==========================================================================
    'LNS14000002': SeriesInfo(
        id='LNS14000002',
        name='Unemployment Rate: Women',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        short_description='Jobless rate for women 16+. Usually tracks the overall rate but can diverge during sector-specific shocks.',
        bullets=[
            'Unemployment rate for women aged 16 and over.',
            'Typically tracks closely with the overall rate but can diverge during sector-specific shocks.'
        ]
    ),
    'LNS12300062': SeriesInfo(
        id='LNS12300062',
        name='Employment-Population Ratio: Women (Prime Age)',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        short_description='% of women aged 25-54 who are employed. Has risen steadily over decades as more women entered the workforce.',
        bullets=[
            'Share of prime-age women (25-54) who are employed.',
            'Has risen steadily as women\'s labor force participation increased.'
        ]
    ),
    'LNS11300002': SeriesInfo(
        id='LNS11300002',
        name='Labor Force Participation Rate: Women',
        unit='Percent',
        source='U.S. Bureau of Labor Statistics',
        data_type='rate',
        short_description='% of adult women working or looking for work. Rose from 43% in 1970 to ~57% today.',
        bullets=[
            'Share of adult women in the labor force.',
            'Rose from 43% in 1970 to around 57% today.'
        ]
    ),
}


# =============================================================================
# QUERY MAP - Fast keyword -> series mappings
# =============================================================================

QUERY_MAP: Dict[str, dict] = {
    # Economy overview - show the big picture (annual GDP for stability)
    'economy': {'series': ['A191RO1Q156NBEA', 'UNRATE', 'CPIAUCSL'], 'combine': False},
    'how is the economy': {'series': ['A191RO1Q156NBEA', 'UNRATE', 'CPIAUCSL'], 'combine': False},
    'economic overview': {'series': ['A191RO1Q156NBEA', 'UNRATE', 'CPIAUCSL'], 'combine': False},
    'recession': {'series': ['A191RO1Q156NBEA', 'UNRATE', 'T10Y2Y'], 'combine': False},

    # Jobs - start simple with payrolls + unemployment
    'job market': {'series': ['PAYEMS', 'UNRATE'], 'combine': False},
    'jobs': {'series': ['PAYEMS', 'UNRATE'], 'combine': False},
    'employment': {'series': ['PAYEMS', 'UNRATE'], 'combine': False},
    'labor market': {'series': ['PAYEMS', 'UNRATE'], 'combine': False},
    'unemployment': {'series': ['UNRATE'], 'combine': False},
    'hiring': {'series': ['PAYEMS', 'JTSJOL'], 'combine': False},
    'job openings': {'series': ['JTSJOL'], 'combine': False},

    # Labor market health (deeper) - use prime-age
    'labor market health': {'series': ['LNS12300060', 'UNRATE'], 'combine': False},
    'labor market tight': {'series': ['LNS12300060', 'JTSJOL', 'UNRATE'], 'combine': False},
    'participation': {'series': ['LNS11300060', 'LNS11300000'], 'combine': True},
    'prime age': {'series': ['LNS12300060'], 'combine': False},

    # Inflation - CPI for general, PCE for Fed
    'inflation': {'series': ['CPIAUCSL', 'CPILFESL'], 'combine': True, 'show_yoy': True},
    'cpi': {'series': ['CPIAUCSL'], 'combine': False, 'show_yoy': True},
    'core inflation': {'series': ['CPILFESL'], 'combine': False, 'show_yoy': True},
    'pce': {'series': ['PCEPI', 'PCEPILFE'], 'combine': True, 'show_yoy': True},
    'fed inflation': {'series': ['PCEPILFE'], 'combine': False, 'show_yoy': True},
    'rent inflation': {'series': ['CUSR0000SAH1'], 'show_yoy': True, 'combine': False},
    'shelter': {'series': ['CUSR0000SAH1'], 'show_yoy': True, 'combine': False},
    'rents': {'series': ['CUSR0000SEHA', 'CUSR0000SAH1'], 'show_yoy': True, 'combine': True},
    'rent': {'series': ['CUSR0000SEHA', 'CUSR0000SAH1'], 'show_yoy': True, 'combine': True},
    'how have rents changed': {'series': ['CUSR0000SEHA', 'CUSR0000SAH1'], 'show_yoy': True, 'combine': True},
    'rental prices': {'series': ['CUSR0000SEHA', 'CUSR0000SAH1'], 'show_yoy': True, 'combine': True},

    # GDP - Annual (YoY), quarterly, core GDP, and GDPNow
    'gdp': {'series': ['A191RL1Q225SBEA', 'PB0000031Q225SBEA', 'GDPNOW'], 'combine': False},
    'gdp growth': {'series': ['A191RL1Q225SBEA', 'PB0000031Q225SBEA', 'GDPNOW'], 'combine': False},
    'economic growth': {'series': ['A191RL1Q225SBEA', 'PB0000031Q225SBEA', 'GDPNOW'], 'combine': False},
    'real gdp': {'series': ['GDPC1'], 'combine': False},
    'annual gdp': {'series': ['A191RL1A225NBEA', 'A191RO1Q156NBEA'], 'combine': False},
    'annual gdp growth': {'series': ['A191RL1A225NBEA', 'A191RO1Q156NBEA'], 'combine': False},
    'yearly gdp': {'series': ['A191RL1A225NBEA', 'A191RO1Q156NBEA'], 'combine': False},
    'core gdp': {'series': ['PB0000031Q225SBEA'], 'combine': False},
    'private demand': {'series': ['PB0000031Q225SBEA'], 'combine': False},
    'final sales': {'series': ['PB0000031Q225SBEA'], 'combine': False},

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
    'consumer': {'series': ['RSXFS', 'UMCSENT'], 'combine': False},
    'consumer sentiment': {'series': ['UMCSENT'], 'combine': False},
    'retail sales': {'series': ['RSXFS'], 'combine': False, 'show_yoy': True},

    # Stocks
    'stock market': {'series': ['SP500'], 'combine': False},
    'stocks': {'series': ['SP500'], 'combine': False},

    # Demographics
    'women': {'series': ['LNS14000002', 'LNS12300062', 'LNS11300002'], 'combine': False},
    'women labor': {'series': ['LNS14000002', 'LNS12300062', 'LNS11300002'], 'combine': False},
    'women employment': {'series': ['LNS14000002', 'LNS12300062'], 'combine': False},

    # Trade & Commodities
    'oil': {'series': ['DCOILWTICO', 'DCOILBRENTEU'], 'combine': True},
    'oil prices': {'series': ['DCOILWTICO', 'DCOILBRENTEU'], 'combine': True},

    # Trade Overview - show balance, imports, and exports together
    'trade': {'series': ['BOPGSTB', 'IMPGS', 'EXPGS'], 'combine': False, 'show_yoy': False},
    'trade balance': {'series': ['BOPGSTB', 'IMPGS', 'EXPGS'], 'combine': False, 'show_yoy': False},
    'trade deficit': {'series': ['BOPGSTB', 'IMPGS', 'EXPGS'], 'combine': False, 'show_yoy': False},
    'trade surplus': {'series': ['BOPGSTB', 'IMPGS', 'EXPGS'], 'combine': False, 'show_yoy': False},
    'imports': {'series': ['IMPGS', 'BOPGSTB'], 'combine': False, 'show_yoy': False},
    'exports': {'series': ['EXPGS', 'BOPGSTB'], 'combine': False, 'show_yoy': False},
    'imports and exports': {'series': ['IMPGS', 'EXPGS', 'BOPGSTB'], 'combine': False, 'show_yoy': False},

    # Trade by Category - Goods vs Services
    'goods trade': {'series': ['BOPGTB', 'IMGION', 'EXGION'], 'combine': False, 'show_yoy': False},
    'services trade': {'series': ['BOPSTB', 'BOPSTXSVCS', 'BOPSTMSVCS'], 'combine': False, 'show_yoy': False},
    'trade by category': {'series': ['BOPGTB', 'BOPSTB', 'BOPGSTB'], 'combine': False, 'show_yoy': False},

    # China Trade (bilateral)
    'china': {'series': ['IMPCH', 'EXPCH', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'china trade': {'series': ['IMPCH', 'EXPCH', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'trade with china': {'series': ['IMPCH', 'EXPCH', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'us china trade': {'series': ['IMPCH', 'EXPCH', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'imports from china': {'series': ['IMPCH'], 'combine': False, 'show_yoy': False},
    'exports to china': {'series': ['EXPCH'], 'combine': False, 'show_yoy': False},

    # Mexico Trade
    'mexico trade': {'series': ['IMPMX', 'EXPMX', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'trade with mexico': {'series': ['IMPMX', 'EXPMX', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'imports from mexico': {'series': ['IMPMX'], 'combine': False, 'show_yoy': False},
    'exports to mexico': {'series': ['EXPMX'], 'combine': False, 'show_yoy': False},

    # Canada Trade
    'canada trade': {'series': ['IMPCA', 'EXPCA', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'trade with canada': {'series': ['IMPCA', 'EXPCA', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'imports from canada': {'series': ['IMPCA'], 'combine': False, 'show_yoy': False},
    'exports from canada': {'series': ['EXPCA'], 'combine': False, 'show_yoy': False},

    # Japan Trade
    'japan trade': {'series': ['IMPJP', 'EXPJP', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'trade with japan': {'series': ['IMPJP', 'EXPJP', 'BOPGTB'], 'combine': False, 'show_yoy': False},

    # EU Trade
    'eu trade': {'series': ['IMPEU', 'EXPEU', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'trade with europe': {'series': ['IMPEU', 'EXPEU', 'BOPGTB'], 'combine': False, 'show_yoy': False},
    'trade with eu': {'series': ['IMPEU', 'EXPEU', 'BOPGTB'], 'combine': False, 'show_yoy': False},

    # Major Trading Partners Overview
    'trading partners': {'series': ['IMPCH', 'IMPMX', 'IMPCA', 'IMPEU'], 'combine': False, 'show_yoy': False},
    'top trading partners': {'series': ['IMPCH', 'IMPMX', 'IMPCA', 'IMPEU'], 'combine': False, 'show_yoy': False},

    # Wages
    'wages': {'series': ['CES0500000003'], 'combine': False},
    'earnings': {'series': ['CES0500000003'], 'combine': False},

    # International comparisons - FRED has this data!
    'us vs europe': {'series': ['A191RL1Q225SBEA', 'CLVMNACSCAB1GQEA19', 'UNRATE', 'LRHUTTTTEZM156S'], 'show_yoy': False, 'combine': False},
    'us vs eurozone': {'series': ['A191RL1Q225SBEA', 'CLVMNACSCAB1GQEA19', 'UNRATE', 'LRHUTTTTEZM156S'], 'show_yoy': False, 'combine': False},
    'us v europe': {'series': ['A191RL1Q225SBEA', 'CLVMNACSCAB1GQEA19', 'UNRATE', 'LRHUTTTTEZM156S'], 'show_yoy': False, 'combine': False},
    'us v eurozone': {'series': ['A191RL1Q225SBEA', 'CLVMNACSCAB1GQEA19', 'UNRATE', 'LRHUTTTTEZM156S'], 'show_yoy': False, 'combine': False},
    'europe economy': {'series': ['CLVMNACSCAB1GQEA19', 'LRHUTTTTEZM156S', 'EA19CPALTT01GYM'], 'show_yoy': False, 'combine': False},
    'eurozone economy': {'series': ['CLVMNACSCAB1GQEA19', 'LRHUTTTTEZM156S', 'EA19CPALTT01GYM'], 'show_yoy': False, 'combine': False},
    'eurozone': {'series': ['CLVMNACSCAB1GQEA19', 'LRHUTTTTEZM156S', 'EA19CPALTT01GYM'], 'show_yoy': False, 'combine': False},
    'europe': {'series': ['CLVMNACSCAB1GQEA19', 'LRHUTTTTEZM156S', 'EA19CPALTT01GYM'], 'show_yoy': False, 'combine': False},
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
            'plans_social.json',
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

        # Load international plans from dbnomics module
        try:
            from agents.dbnomics import INTERNATIONAL_QUERY_PLANS
            self._plans.update(INTERNATIONAL_QUERY_PLANS)
            print(f"[Registry] Loaded {len(INTERNATIONAL_QUERY_PLANS)} international plans from dbnomics")
        except Exception as e:
            print(f"[Registry] International plans not available: {e}")

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
