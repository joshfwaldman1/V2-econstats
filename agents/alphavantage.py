"""
Alpha Vantage data integration for EconStats.

Provides access to financial data including:
- Stock prices (daily, weekly, intraday)
- Economic indicators (GDP, CPI, unemployment, etc.)
- Treasury yields
- Commodities (crude oil, natural gas, etc.)
- Forex rates

API Documentation: https://www.alphavantage.co/documentation/
Free API Key: https://www.alphavantage.co/support/#api-key
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

# API Key from environment
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")

# Base URL
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"

# =============================================================================
# ALPHA VANTAGE SERIES CATALOG
# =============================================================================

ALPHAVANTAGE_SERIES = {
    # ==========================================================================
    # STOCK INDICES (represented by ETFs that track them)
    # ==========================================================================
    'av_spy': {
        'name': 'S&P 500 (SPY ETF)',
        'description': 'SPDR S&P 500 ETF Trust - tracks the S&P 500 index',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'SPY',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['sp500', 's&p', 'stocks', 'market', 'equity', 'index'],
        'fred_equivalent': 'SP500',
    },
    'av_qqq': {
        'name': 'Nasdaq 100 (QQQ ETF)',
        'description': 'Invesco QQQ Trust - tracks the Nasdaq-100 index',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'QQQ',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['nasdaq', 'tech', 'stocks', 'market', 'equity', 'technology'],
        'fred_equivalent': 'NASDAQCOM',
    },
    'av_dia': {
        'name': 'Dow Jones (DIA ETF)',
        'description': 'SPDR Dow Jones Industrial Average ETF',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'DIA',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['dow', 'djia', 'stocks', 'market', 'equity', 'industrials'],
        'fred_equivalent': 'DJIA',
    },
    'av_iwm': {
        'name': 'Russell 2000 (IWM ETF)',
        'description': 'iShares Russell 2000 ETF - tracks small-cap stocks',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'IWM',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['russell', 'small cap', 'stocks', 'market', 'equity'],
    },
    'av_vix': {
        'name': 'VIX Volatility (VXX)',
        'description': 'iPath Series B S&P 500 VIX Short-Term Futures ETN',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'VXX',
        'units': 'index',
        'frequency': 'daily',
        'measure_type': 'index',
        'change_type': 'level',
        'keywords': ['vix', 'volatility', 'fear', 'risk', 'market'],
        'fred_equivalent': 'VIXCLS',
    },

    # ==========================================================================
    # MAGNIFICENT 7 STOCKS (Individual Mag7 Companies)
    # ==========================================================================
    'av_aapl': {
        'name': 'Apple (AAPL)',
        'description': 'Apple Inc. - Consumer electronics, software, and services. iPhone, Mac, iPad, Services.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'AAPL',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['apple', 'aapl', 'iphone', 'mac', 'mag7', 'magnificent 7', 'big tech', 'tech stock'],
    },
    'av_msft': {
        'name': 'Microsoft (MSFT)',
        'description': 'Microsoft Corporation - Enterprise software, cloud (Azure), gaming (Xbox), AI (OpenAI partnership).',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'MSFT',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['microsoft', 'msft', 'azure', 'windows', 'mag7', 'magnificent 7', 'big tech', 'tech stock', 'ai'],
    },
    'av_googl': {
        'name': 'Alphabet/Google (GOOGL)',
        'description': 'Alphabet Inc. - Search, advertising, YouTube, Google Cloud, Waymo, DeepMind AI.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'GOOGL',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['google', 'alphabet', 'googl', 'youtube', 'mag7', 'magnificent 7', 'big tech', 'tech stock', 'search', 'ai'],
    },
    'av_amzn': {
        'name': 'Amazon (AMZN)',
        'description': 'Amazon.com Inc. - E-commerce, AWS cloud, Prime streaming, advertising, logistics.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'AMZN',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['amazon', 'amzn', 'aws', 'prime', 'mag7', 'magnificent 7', 'big tech', 'ecommerce', 'cloud'],
    },
    'av_nvda': {
        'name': 'NVIDIA (NVDA)',
        'description': 'NVIDIA Corporation - GPUs, AI chips, data center accelerators. Leading AI infrastructure provider.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'NVDA',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['nvidia', 'nvda', 'gpu', 'ai chips', 'mag7', 'magnificent 7', 'big tech', 'tech stock', 'ai', 'semiconductors'],
    },
    'av_meta': {
        'name': 'Meta Platforms (META)',
        'description': 'Meta Platforms Inc. - Facebook, Instagram, WhatsApp, Threads, Reality Labs VR/AR.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'META',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['meta', 'facebook', 'instagram', 'whatsapp', 'mag7', 'magnificent 7', 'big tech', 'tech stock', 'social media'],
    },
    'av_tsla': {
        'name': 'Tesla (TSLA)',
        'description': 'Tesla Inc. - Electric vehicles, energy storage, solar, autonomous driving, AI.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'TSLA',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['tesla', 'tsla', 'ev', 'electric vehicle', 'mag7', 'magnificent 7', 'big tech', 'elon musk', 'auto'],
    },

    # ==========================================================================
    # ECONOMIC INDICATORS
    # ==========================================================================
    'av_real_gdp': {
        'name': 'Real GDP (Alpha Vantage)',
        'description': 'US Real Gross Domestic Product, quarterly',
        'function': 'REAL_GDP',
        'interval': 'quarterly',
        'units': 'billions of dollars',
        'frequency': 'quarterly',
        'measure_type': 'real',
        'change_type': 'level',
        'keywords': ['gdp', 'growth', 'economy', 'output', 'production'],
        'fred_equivalent': 'GDPC1',
    },
    'av_cpi': {
        'name': 'CPI (Alpha Vantage)',
        'description': 'Consumer Price Index for all urban consumers',
        'function': 'CPI',
        'interval': 'monthly',
        'units': 'index',
        'frequency': 'monthly',
        'measure_type': 'index',
        'change_type': 'level',
        'keywords': ['cpi', 'inflation', 'prices', 'consumer'],
        'fred_equivalent': 'CPIAUCSL',
    },
    'av_inflation': {
        'name': 'Inflation Rate (Alpha Vantage)',
        'description': 'Annual inflation rate based on consumer prices',
        'function': 'INFLATION',
        'units': 'percent',
        'frequency': 'annual',
        'measure_type': 'rate',
        'change_type': 'yoy',
        'keywords': ['inflation', 'prices', 'cost of living'],
    },
    'av_unemployment': {
        'name': 'Unemployment Rate (Alpha Vantage)',
        'description': 'US unemployment rate',
        'function': 'UNEMPLOYMENT',
        'units': 'percent',
        'frequency': 'monthly',
        'measure_type': 'rate',
        'change_type': 'level',
        'keywords': ['unemployment', 'jobs', 'labor', 'jobless'],
        'fred_equivalent': 'UNRATE',
    },
    'av_fed_funds': {
        'name': 'Federal Funds Rate (Alpha Vantage)',
        'description': 'Effective federal funds rate',
        'function': 'FEDERAL_FUNDS_RATE',
        'interval': 'monthly',
        'units': 'percent',
        'frequency': 'monthly',
        'measure_type': 'rate',
        'change_type': 'level',
        'keywords': ['fed', 'interest rate', 'fomc', 'federal reserve', 'rates'],
        'fred_equivalent': 'FEDFUNDS',
    },
    'av_consumer_sentiment': {
        'name': 'Consumer Sentiment (Alpha Vantage)',
        'description': 'University of Michigan Consumer Sentiment Index',
        'function': 'CONSUMER_SENTIMENT',
        'units': 'index',
        'frequency': 'monthly',
        'measure_type': 'index',
        'change_type': 'level',
        'keywords': ['sentiment', 'consumer', 'confidence', 'survey'],
        'fred_equivalent': 'UMCSENT',
    },
    'av_retail_sales': {
        'name': 'Retail Sales (Alpha Vantage)',
        'description': 'US monthly retail sales',
        'function': 'RETAIL_SALES',
        'units': 'millions of dollars',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['retail', 'sales', 'consumer', 'spending', 'shopping'],
        'fred_equivalent': 'RSXFS',
    },
    'av_nonfarm_payroll': {
        'name': 'Nonfarm Payrolls (Alpha Vantage)',
        'description': 'Total nonfarm employment',
        'function': 'NONFARM_PAYROLL',
        'units': 'thousands of persons',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['payrolls', 'jobs', 'employment', 'labor', 'jobs report'],
        'fred_equivalent': 'PAYEMS',
    },

    # ==========================================================================
    # TREASURY YIELDS
    # ==========================================================================
    'av_treasury_10y': {
        'name': '10-Year Treasury Yield',
        'description': 'US 10-Year Treasury Bond Yield',
        'function': 'TREASURY_YIELD',
        'interval': 'daily',
        'maturity': '10year',
        'units': 'percent',
        'frequency': 'daily',
        'measure_type': 'rate',
        'change_type': 'level',
        'keywords': ['treasury', 'bond', 'yield', '10 year', 'rates'],
        'fred_equivalent': 'DGS10',
    },
    'av_treasury_2y': {
        'name': '2-Year Treasury Yield',
        'description': 'US 2-Year Treasury Bond Yield',
        'function': 'TREASURY_YIELD',
        'interval': 'daily',
        'maturity': '2year',
        'units': 'percent',
        'frequency': 'daily',
        'measure_type': 'rate',
        'change_type': 'level',
        'keywords': ['treasury', 'bond', 'yield', '2 year', 'rates', 'short term'],
        'fred_equivalent': 'DGS2',
    },
    'av_treasury_30y': {
        'name': '30-Year Treasury Yield',
        'description': 'US 30-Year Treasury Bond Yield',
        'function': 'TREASURY_YIELD',
        'interval': 'daily',
        'maturity': '30year',
        'units': 'percent',
        'frequency': 'daily',
        'measure_type': 'rate',
        'change_type': 'level',
        'keywords': ['treasury', 'bond', 'yield', '30 year', 'rates', 'long term'],
        'fred_equivalent': 'DGS30',
    },
    'av_treasury_3m': {
        'name': '3-Month Treasury Yield',
        'description': 'US 3-Month Treasury Bill Yield',
        'function': 'TREASURY_YIELD',
        'interval': 'daily',
        'maturity': '3month',
        'units': 'percent',
        'frequency': 'daily',
        'measure_type': 'rate',
        'change_type': 'level',
        'keywords': ['treasury', 'bill', 'yield', '3 month', 'rates', 'short term'],
        'fred_equivalent': 'DGS3MO',
    },

    # ==========================================================================
    # COMMODITIES
    # ==========================================================================
    'av_crude_oil': {
        'name': 'WTI Crude Oil',
        'description': 'West Texas Intermediate crude oil price',
        'function': 'WTI',
        'interval': 'daily',
        'units': 'dollars per barrel',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['oil', 'crude', 'wti', 'energy', 'petroleum'],
        'fred_equivalent': 'DCOILWTICO',
    },
    'av_brent': {
        'name': 'Brent Crude Oil',
        'description': 'Brent crude oil price',
        'function': 'BRENT',
        'interval': 'daily',
        'units': 'dollars per barrel',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['oil', 'crude', 'brent', 'energy', 'petroleum', 'europe'],
        'fred_equivalent': 'DCOILBRENTEU',
    },
    'av_natural_gas': {
        'name': 'Natural Gas',
        'description': 'Henry Hub natural gas spot price',
        'function': 'NATURAL_GAS',
        'interval': 'daily',
        'units': 'dollars per MMBtu',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['natural gas', 'gas', 'energy', 'henry hub'],
        'fred_equivalent': 'DHHNGSP',
    },
    'av_gold': {
        'name': 'Gold Price',
        'description': 'Gold spot price per troy ounce',
        'function': 'CURRENCY_EXCHANGE_RATE',
        'from_currency': 'XAU',
        'to_currency': 'USD',
        'is_commodity': True,
        'units': 'dollars per troy ounce',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gold', 'precious metal', 'commodity', 'safe haven'],
        'fred_equivalent': 'GOLDAMGBD228NLBM',
    },

    # ==========================================================================
    # FOREX
    # ==========================================================================
    'av_eurusd': {
        'name': 'EUR/USD Exchange Rate',
        'description': 'Euro to US Dollar exchange rate',
        'function': 'FX_DAILY',
        'from_symbol': 'EUR',
        'to_symbol': 'USD',
        'units': 'dollars per euro',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['euro', 'dollar', 'forex', 'currency', 'exchange rate'],
        'fred_equivalent': 'DEXUSEU',
    },
    'av_usdjpy': {
        'name': 'USD/JPY Exchange Rate',
        'description': 'US Dollar to Japanese Yen exchange rate',
        'function': 'FX_DAILY',
        'from_symbol': 'USD',
        'to_symbol': 'JPY',
        'units': 'yen per dollar',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['yen', 'dollar', 'forex', 'currency', 'exchange rate', 'japan'],
        'fred_equivalent': 'DEXJPUS',
    },
    'av_gbpusd': {
        'name': 'GBP/USD Exchange Rate',
        'description': 'British Pound to US Dollar exchange rate',
        'function': 'FX_DAILY',
        'from_symbol': 'GBP',
        'to_symbol': 'USD',
        'units': 'dollars per pound',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['pound', 'sterling', 'dollar', 'forex', 'currency', 'uk', 'britain'],
        'fred_equivalent': 'DEXUSUK',
    },
    'av_dollar_index': {
        'name': 'US Dollar Index (UUP ETF)',
        'description': 'Invesco DB US Dollar Index Bullish Fund - tracks USD vs basket',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'UUP',
        'units': 'index',
        'frequency': 'daily',
        'measure_type': 'index',
        'change_type': 'level',
        'keywords': ['dollar', 'usd', 'dxy', 'currency', 'forex', 'dollar index'],
        'fred_equivalent': 'DTWEXBGS',
    },

    # ==========================================================================
    # SECTOR ETFs (SPDR Select Sector Funds - S&P 500 Sector Breakdown)
    # ==========================================================================
    'av_xlf': {
        'name': 'Financial Sector (XLF ETF)',
        'description': 'Financial Select Sector SPDR Fund - tracks S&P 500 financial stocks including banks, insurance, and capital markets. Top holdings include Berkshire Hathaway, JPMorgan, Bank of America.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLF',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['financial', 'banks', 'insurance', 'sector', 'finance', 'banking', 'wall street', 'xlf'],
    },
    'av_xle': {
        'name': 'Energy Sector (XLE ETF)',
        'description': 'Energy Select Sector SPDR Fund - tracks S&P 500 energy stocks including oil, gas, and consumable fuels. Top holdings include Exxon Mobil, Chevron.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLE',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['energy', 'oil', 'gas', 'sector', 'petroleum', 'xle', 'exxon', 'chevron'],
    },
    'av_xlv': {
        'name': 'Healthcare Sector (XLV ETF)',
        'description': 'Health Care Select Sector SPDR Fund - tracks S&P 500 healthcare stocks including pharmaceuticals, biotech, and medical devices. Top holdings include UnitedHealth, Eli Lilly, Johnson & Johnson.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLV',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['healthcare', 'health', 'pharma', 'biotech', 'medical', 'sector', 'xlv', 'drugs'],
    },
    'av_xlk': {
        'name': 'Technology Sector (XLK ETF)',
        'description': 'Technology Select Sector SPDR Fund - tracks S&P 500 technology stocks including software, hardware, and semiconductors. Top holdings include Apple, Microsoft, NVIDIA.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLK',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['technology', 'tech', 'software', 'hardware', 'sector', 'xlk', 'apple', 'microsoft', 'semiconductors'],
    },
    'av_xli': {
        'name': 'Industrial Sector (XLI ETF)',
        'description': 'Industrial Select Sector SPDR Fund - tracks S&P 500 industrial stocks including aerospace, defense, machinery, and transportation. Top holdings include GE Aerospace, Caterpillar, RTX.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLI',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['industrial', 'industrials', 'manufacturing', 'sector', 'xli', 'aerospace', 'defense', 'machinery'],
    },
    'av_xlu': {
        'name': 'Utilities Sector (XLU ETF)',
        'description': 'Utilities Select Sector SPDR Fund - tracks S&P 500 utility stocks including electric, gas, and water utilities. Defensive sector with dividend income focus.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLU',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['utilities', 'utility', 'electric', 'power', 'sector', 'xlu', 'defensive', 'dividend'],
    },
    'av_xlp': {
        'name': 'Consumer Staples Sector (XLP ETF)',
        'description': 'Consumer Staples Select Sector SPDR Fund - tracks S&P 500 consumer staples stocks including food, beverages, and household products. Top holdings include Procter & Gamble, Costco, Walmart.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLP',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['consumer staples', 'staples', 'food', 'beverage', 'sector', 'xlp', 'defensive', 'grocery'],
    },
    'av_xly': {
        'name': 'Consumer Discretionary Sector (XLY ETF)',
        'description': 'Consumer Discretionary Select Sector SPDR Fund - tracks S&P 500 consumer discretionary stocks including retail, automobiles, and leisure. Top holdings include Amazon, Tesla, Home Depot.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLY',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['consumer discretionary', 'retail', 'auto', 'sector', 'xly', 'amazon', 'tesla', 'spending'],
    },
    'av_xlb': {
        'name': 'Materials Sector (XLB ETF)',
        'description': 'Materials Select Sector SPDR Fund - tracks S&P 500 materials stocks including chemicals, metals, mining, and packaging. Top holdings include Linde, Sherwin-Williams, Freeport-McMoRan.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLB',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['materials', 'chemicals', 'metals', 'mining', 'sector', 'xlb', 'commodities', 'copper'],
    },
    'av_xlre': {
        'name': 'Real Estate Sector (XLRE ETF)',
        'description': 'Real Estate Select Sector SPDR Fund - tracks S&P 500 real estate stocks including REITs for data centers, cell towers, and commercial real estate. Top holdings include Prologis, American Tower.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLRE',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['real estate', 'reit', 'property', 'sector', 'xlre', 'data center', 'commercial'],
    },
    'av_xlc': {
        'name': 'Communications Sector (XLC ETF)',
        'description': 'Communication Services Select Sector SPDR Fund - tracks S&P 500 communication services stocks including media, telecom, and entertainment. Top holdings include Meta, Alphabet, Netflix.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'XLC',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['communication', 'media', 'telecom', 'sector', 'xlc', 'facebook', 'google', 'streaming'],
    },

    # ==========================================================================
    # INTERNATIONAL ETFs (Global Market Exposure)
    # ==========================================================================
    'av_eem': {
        'name': 'Emerging Markets (EEM ETF)',
        'description': 'iShares MSCI Emerging Markets ETF - tracks large and mid-cap emerging market equities across China, Taiwan, India, South Korea, Brazil, and other developing economies.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'EEM',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['emerging markets', 'em', 'international', 'china', 'india', 'brazil', 'developing', 'eem'],
    },
    'av_efa': {
        'name': 'Developed Markets ex-US (EFA ETF)',
        'description': 'iShares MSCI EAFE ETF - tracks developed market equities in Europe, Australasia, and Far East excluding US and Canada. Includes Japan, UK, France, Germany, Switzerland.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'EFA',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['developed markets', 'eafe', 'international', 'europe', 'japan', 'uk', 'efa', 'foreign'],
    },
    'av_fxi': {
        'name': 'China Large-Cap (FXI ETF)',
        'description': 'iShares China Large-Cap ETF - tracks 50 of the largest Chinese companies listed on the Hong Kong Stock Exchange, including Alibaba, Tencent, China Construction Bank.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'FXI',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['china', 'chinese', 'hong kong', 'fxi', 'asia', 'emerging', 'alibaba', 'tencent'],
    },
    'av_vwo': {
        'name': 'Emerging Markets (VWO ETF)',
        'description': 'Vanguard FTSE Emerging Markets ETF - broad emerging market exposure including China, Taiwan, India, Brazil, South Africa. Lower cost alternative to EEM.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'VWO',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['emerging markets', 'em', 'vanguard', 'international', 'developing', 'vwo'],
    },
    'av_ewj': {
        'name': 'Japan (EWJ ETF)',
        'description': 'iShares MSCI Japan ETF - tracks large and mid-cap Japanese equities including Toyota, Sony, Mitsubishi. Exposure to the third-largest economy.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'EWJ',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['japan', 'japanese', 'nikkei', 'ewj', 'asia', 'toyota', 'yen'],
    },
    'av_ewg': {
        'name': 'Germany (EWG ETF)',
        'description': 'iShares MSCI Germany ETF - tracks large and mid-cap German equities including SAP, Siemens, Allianz. Exposure to Europe\'s largest economy.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'EWG',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['germany', 'german', 'dax', 'ewg', 'europe', 'siemens', 'euro'],
    },
    'av_ewu': {
        'name': 'United Kingdom (EWU ETF)',
        'description': 'iShares MSCI United Kingdom ETF - tracks large and mid-cap UK equities including Shell, AstraZeneca, HSBC. Exposure to UK economy post-Brexit.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'EWU',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['uk', 'united kingdom', 'britain', 'ftse', 'ewu', 'europe', 'pound', 'london'],
    },

    # ==========================================================================
    # BOND ETFs (Fixed Income Exposure)
    # ==========================================================================
    'av_tlt': {
        'name': 'Long-Term Treasuries (TLT ETF)',
        'description': 'iShares 20+ Year Treasury Bond ETF - tracks US Treasury bonds with 20+ years maturity. Highly sensitive to interest rate changes, often rises when stocks fall.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'TLT',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['treasury', 'bond', 'tlt', 'long term', 'rates', 'duration', 'safe haven', 'fixed income'],
    },
    'av_shy': {
        'name': 'Short-Term Treasuries (SHY ETF)',
        'description': 'iShares 1-3 Year Treasury Bond ETF - tracks US Treasury bonds with 1-3 years maturity. Low duration, minimal interest rate sensitivity, cash alternative.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'SHY',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['treasury', 'bond', 'shy', 'short term', 'rates', 'cash', 'fixed income', 'safe'],
    },
    'av_ief': {
        'name': 'Intermediate Treasuries (IEF ETF)',
        'description': 'iShares 7-10 Year Treasury Bond ETF - tracks US Treasury bonds with 7-10 years maturity. Moderate duration, balanced interest rate sensitivity.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'IEF',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['treasury', 'bond', 'ief', 'intermediate', 'rates', 'duration', 'fixed income'],
    },
    'av_hyg': {
        'name': 'High Yield Corporate Bonds (HYG ETF)',
        'description': 'iShares iBoxx High Yield Corporate Bond ETF - tracks USD-denominated high yield (junk) corporate bonds. Higher yield but credit risk, sensitive to economic conditions.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'HYG',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['high yield', 'junk bonds', 'corporate', 'hyg', 'credit', 'risk', 'spread', 'fixed income'],
    },
    'av_lqd': {
        'name': 'Investment Grade Corporate Bonds (LQD ETF)',
        'description': 'iShares iBoxx Investment Grade Corporate Bond ETF - tracks USD-denominated investment grade corporate bonds. Lower risk than high yield, quality credit.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'LQD',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['investment grade', 'corporate', 'lqd', 'credit', 'quality', 'fixed income', 'bonds'],
    },
    'av_agg': {
        'name': 'Aggregate Bond Market (AGG ETF)',
        'description': 'iShares Core US Aggregate Bond ETF - tracks the total US investment-grade bond market including Treasuries, corporates, and mortgage-backed securities.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'AGG',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['aggregate', 'bond', 'agg', 'total bond', 'fixed income', 'diversified', 'core'],
    },
    'av_tip': {
        'name': 'TIPS Inflation-Protected (TIP ETF)',
        'description': 'iShares TIPS Bond ETF - tracks US Treasury Inflation-Protected Securities. Principal adjusts with CPI, protection against inflation.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'TIP',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['tips', 'inflation', 'treasury', 'protected', 'real', 'cpi', 'fixed income'],
    },

    # ==========================================================================
    # COMMODITY ETFs (Physical and Futures-Based)
    # ==========================================================================
    'av_gld': {
        'name': 'Gold (GLD ETF)',
        'description': 'SPDR Gold Shares - physically backed gold ETF, tracks spot gold price. Safe haven asset during market stress, inflation hedge.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'GLD',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gold', 'precious metal', 'gld', 'safe haven', 'inflation', 'commodity', 'bullion'],
    },
    'av_slv': {
        'name': 'Silver (SLV ETF)',
        'description': 'iShares Silver Trust - physically backed silver ETF, tracks spot silver price. Industrial metal with precious metal characteristics.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'SLV',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['silver', 'precious metal', 'slv', 'industrial', 'commodity', 'bullion'],
    },
    'av_uso': {
        'name': 'Crude Oil (USO ETF)',
        'description': 'United States Oil Fund - tracks WTI crude oil futures. Exposure to oil price movements, affected by contango/backwardation.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'USO',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['oil', 'crude', 'uso', 'wti', 'petroleum', 'energy', 'commodity', 'futures'],
    },
    'av_ung': {
        'name': 'Natural Gas (UNG ETF)',
        'description': 'United States Natural Gas Fund - tracks natural gas futures. Volatile commodity exposure, weather-dependent demand.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'UNG',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['natural gas', 'gas', 'ung', 'energy', 'commodity', 'futures', 'henry hub'],
    },
    'av_dba': {
        'name': 'Agriculture (DBA ETF)',
        'description': 'Invesco DB Agriculture Fund - tracks diversified agricultural commodity futures including corn, wheat, soybeans, sugar, coffee, cocoa.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'DBA',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['agriculture', 'farm', 'dba', 'corn', 'wheat', 'soybeans', 'food', 'commodity'],
    },
    'av_dbc': {
        'name': 'Commodities Broad (DBC ETF)',
        'description': 'Invesco DB Commodity Index Tracking Fund - tracks diversified commodity futures basket including energy, precious metals, industrial metals, and agriculture.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'DBC',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['commodities', 'broad', 'dbc', 'diversified', 'inflation', 'raw materials'],
    },

    # ==========================================================================
    # VOLATILITY & ALTERNATIVES
    # ==========================================================================
    'av_vixy': {
        'name': 'VIX Short-Term (VIXY ETF)',
        'description': 'ProShares VIX Short-Term Futures ETF - tracks VIX short-term futures. Spikes during market fear, significant decay over time.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'VIXY',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'index',
        'change_type': 'level',
        'keywords': ['vix', 'volatility', 'vixy', 'fear', 'hedging', 'market risk', 'protection'],
    },
    'av_uvxy': {
        'name': 'VIX 1.5x Leveraged (UVXY ETF)',
        'description': 'ProShares Ultra VIX Short-Term Futures ETF - 1.5x leveraged VIX exposure. Extreme moves during volatility spikes, rapid decay in calm markets.',
        'function': 'TIME_SERIES_DAILY',
        'symbol': 'UVXY',
        'units': 'dollars',
        'frequency': 'daily',
        'measure_type': 'index',
        'change_type': 'level',
        'keywords': ['vix', 'volatility', 'uvxy', 'leveraged', 'fear', 'hedging', 'spike'],
    },

    # ==========================================================================
    # ADDITIONAL FOREX PAIRS
    # ==========================================================================
    'av_usdcad': {
        'name': 'USD/CAD Exchange Rate',
        'description': 'US Dollar to Canadian Dollar exchange rate. Influenced by oil prices and US-Canada trade relations.',
        'function': 'FX_DAILY',
        'from_symbol': 'USD',
        'to_symbol': 'CAD',
        'units': 'CAD per dollar',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['canada', 'canadian', 'loonie', 'dollar', 'forex', 'currency', 'usdcad', 'nafta'],
    },
    'av_usdchf': {
        'name': 'USD/CHF Exchange Rate',
        'description': 'US Dollar to Swiss Franc exchange rate. Swiss franc is a traditional safe haven currency.',
        'function': 'FX_DAILY',
        'from_symbol': 'USD',
        'to_symbol': 'CHF',
        'units': 'CHF per dollar',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['swiss', 'franc', 'switzerland', 'dollar', 'forex', 'currency', 'usdchf', 'safe haven'],
    },
    'av_audusd': {
        'name': 'AUD/USD Exchange Rate',
        'description': 'Australian Dollar to US Dollar exchange rate. Commodity currency sensitive to China trade and mining.',
        'function': 'FX_DAILY',
        'from_symbol': 'AUD',
        'to_symbol': 'USD',
        'units': 'dollars per AUD',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['australia', 'aussie', 'dollar', 'forex', 'currency', 'audusd', 'commodity'],
    },
    'av_nzdusd': {
        'name': 'NZD/USD Exchange Rate',
        'description': 'New Zealand Dollar to US Dollar exchange rate. Kiwi dollar sensitive to dairy prices and risk appetite.',
        'function': 'FX_DAILY',
        'from_symbol': 'NZD',
        'to_symbol': 'USD',
        'units': 'dollars per NZD',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['new zealand', 'kiwi', 'dollar', 'forex', 'currency', 'nzdusd'],
    },
    'av_usdmxn': {
        'name': 'USD/MXN Exchange Rate',
        'description': 'US Dollar to Mexican Peso exchange rate. Sensitive to US-Mexico trade policy, remittances, and risk sentiment.',
        'function': 'FX_DAILY',
        'from_symbol': 'USD',
        'to_symbol': 'MXN',
        'units': 'pesos per dollar',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['mexico', 'peso', 'dollar', 'forex', 'currency', 'usdmxn', 'trade', 'nafta'],
    },
    'av_usdcny': {
        'name': 'USD/CNY Exchange Rate',
        'description': 'US Dollar to Chinese Yuan (onshore) exchange rate. Managed float currency, key indicator of China-US trade tensions.',
        'function': 'FX_DAILY',
        'from_symbol': 'USD',
        'to_symbol': 'CNY',
        'units': 'yuan per dollar',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['china', 'yuan', 'renminbi', 'dollar', 'forex', 'currency', 'usdcny', 'trade war'],
    },
    'av_eurjpy': {
        'name': 'EUR/JPY Exchange Rate',
        'description': 'Euro to Japanese Yen cross rate. Risk sentiment indicator - rises with global growth optimism.',
        'function': 'FX_DAILY',
        'from_symbol': 'EUR',
        'to_symbol': 'JPY',
        'units': 'yen per euro',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['euro', 'yen', 'japan', 'europe', 'forex', 'currency', 'eurjpy', 'cross'],
    },
    'av_eurgbp': {
        'name': 'EUR/GBP Exchange Rate',
        'description': 'Euro to British Pound cross rate. Key European cross, sensitive to Brexit effects and ECB/BOE policy divergence.',
        'function': 'FX_DAILY',
        'from_symbol': 'EUR',
        'to_symbol': 'GBP',
        'units': 'pounds per euro',
        'frequency': 'daily',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['euro', 'pound', 'sterling', 'europe', 'uk', 'forex', 'currency', 'eurgbp', 'brexit'],
    },
}

# Cache
_cache = {}
_cache_ttl = timedelta(hours=1)

# Rate limiting - Alpha Vantage free tier: 25 requests/day, 5/minute
_rate_limit_daily = 25
_rate_limit_minute = 5
_requests_today = []
_requests_minute = []


def _check_rate_limit() -> bool:
    """
    Check if we're within rate limits.

    Returns True if request is allowed, False if rate limited.
    Cleans up old request timestamps as a side effect.
    """
    global _requests_today, _requests_minute

    now = datetime.now()

    # Clean up old requests (older than 24 hours)
    cutoff_day = now - timedelta(hours=24)
    _requests_today = [t for t in _requests_today if t > cutoff_day]

    # Clean up minute-level tracking (older than 1 minute)
    cutoff_minute = now - timedelta(minutes=1)
    _requests_minute = [t for t in _requests_minute if t > cutoff_minute]

    # Check daily limit
    if len(_requests_today) >= _rate_limit_daily:
        return False

    # Check per-minute limit
    if len(_requests_minute) >= _rate_limit_minute:
        return False

    return True


def _record_request():
    """Record a request for rate limiting purposes."""
    now = datetime.now()
    _requests_today.append(now)
    _requests_minute.append(now)


def get_rate_limit_status() -> dict:
    """Get current rate limit status for debugging."""
    _check_rate_limit()  # Clean up old entries
    return {
        'daily_used': len(_requests_today),
        'daily_limit': _rate_limit_daily,
        'daily_remaining': _rate_limit_daily - len(_requests_today),
        'minute_used': len(_requests_minute),
        'minute_limit': _rate_limit_minute,
    }


def _fetch_alphavantage(params: dict) -> dict:
    """
    Fetch data from Alpha Vantage API.

    Args:
        params: Query parameters including 'function' and 'apikey'

    Returns:
        JSON response dict
    """
    if not ALPHAVANTAGE_API_KEY:
        print("[AlphaVantage] Warning: ALPHAVANTAGE_API_KEY not set. Get a free key at https://www.alphavantage.co/support/#api-key")
        return {'error': 'No API key'}

    params['apikey'] = ALPHAVANTAGE_API_KEY

    # Build URL
    query_string = '&'.join(f"{k}={v}" for k, v in params.items())
    url = f"{ALPHAVANTAGE_BASE_URL}?{query_string}"

    # Check cache
    cache_key = url
    now = datetime.now()
    if cache_key in _cache:
        cached_data, cached_time = _cache[cache_key]
        if now - cached_time < _cache_ttl:
            return cached_data

    # Check rate limits before making API call
    if not _check_rate_limit():
        status = get_rate_limit_status()
        print(f"[AlphaVantage] Rate limited: {status['daily_used']}/{status['daily_limit']} daily requests used")
        return {'error': f"Alpha Vantage rate limit reached ({status['daily_used']}/{status['daily_limit']} daily requests). Try again later or use FRED equivalent series."}

    try:
        # Record this request for rate limiting
        _record_request()
        req = Request(url, headers={'User-Agent': 'EconStats/1.0'})
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))

            # Check for API error messages
            if 'Error Message' in data:
                return {'error': data['Error Message']}
            if 'Note' in data:  # Rate limit message
                return {'error': data['Note']}
            if 'Information' in data:  # API key issue
                return {'error': data['Information']}

            _cache[cache_key] = (data, now)
            return data
    except URLError as e:
        print(f"[AlphaVantage] Error: {e}")
        return {'error': str(e)}
    except json.JSONDecodeError as e:
        print(f"[AlphaVantage] Invalid JSON: {e}")
        return {'error': f"Invalid JSON: {e}"}


def _parse_time_series(data: dict, data_key: str = None) -> tuple:
    """
    Parse time series data from Alpha Vantage response.

    Returns: (dates, values) where dates are strings and values are floats
    """
    # Find the time series key (varies by function)
    ts_key = data_key
    if not ts_key:
        for key in data.keys():
            if 'Time Series' in key or key.startswith('data') or key == 'data':
                ts_key = key
                break

    if not ts_key or ts_key not in data:
        return [], []

    time_series = data[ts_key]

    # Handle different data formats
    if isinstance(time_series, list):
        # Economic indicator format: list of {date, value} dicts
        # API returns descending order (newest first), we need ascending (oldest first)
        pairs = []
        for entry in time_series:
            date = entry.get('date')
            value = entry.get('value')
            if date and value:
                try:
                    pairs.append((date, float(value)))
                except (ValueError, TypeError):
                    continue
        # Sort by date ascending
        pairs.sort(key=lambda x: x[0])
        dates = [p[0] for p in pairs]
        values = [p[1] for p in pairs]
        return dates, values

    elif isinstance(time_series, dict):
        # Time series format: dict of date -> OHLCV
        dates = []
        values = []
        for date_str, ohlcv in sorted(time_series.items()):
            try:
                # Use close price (key varies: '4. close', 'close', etc.)
                value = None
                for key in ['4. close', 'close', '5. adjusted close', 'value']:
                    if key in ohlcv:
                        value = float(ohlcv[key])
                        break

                if value is not None:
                    dates.append(date_str)
                    values.append(value)
            except (ValueError, TypeError):
                continue

        return dates, values

    return [], []


def get_alphavantage_series(series_key: str) -> tuple:
    """
    Fetch an Alpha Vantage series.

    Args:
        series_key: One of the keys in ALPHAVANTAGE_SERIES

    Returns:
        (dates, values, info) tuple compatible with FRED format
    """
    if series_key not in ALPHAVANTAGE_SERIES:
        return [], [], {'error': f"Unknown Alpha Vantage series: {series_key}"}

    series_info = ALPHAVANTAGE_SERIES[series_key]
    function = series_info['function']

    # Build request params based on function type
    params = {'function': function}

    if function == 'TIME_SERIES_DAILY':
        params['symbol'] = series_info['symbol']
        params['outputsize'] = 'compact'  # 'full' requires premium
    elif function in ['TIME_SERIES_WEEKLY', 'TIME_SERIES_MONTHLY']:
        params['symbol'] = series_info['symbol']
    elif function == 'FX_DAILY':
        params['from_symbol'] = series_info['from_symbol']
        params['to_symbol'] = series_info['to_symbol']
    elif function == 'TREASURY_YIELD':
        params['interval'] = series_info.get('interval', 'daily')
        params['maturity'] = series_info['maturity']
    elif function in ['WTI', 'BRENT', 'NATURAL_GAS']:
        params['interval'] = series_info.get('interval', 'daily')
    elif function == 'CURRENCY_EXCHANGE_RATE':
        params['from_currency'] = series_info['from_currency']
        params['to_currency'] = series_info['to_currency']
    elif function in ['REAL_GDP', 'CPI', 'FEDERAL_FUNDS_RATE', 'RETAIL_SALES']:
        if 'interval' in series_info:
            params['interval'] = series_info['interval']
    # Other economic indicators don't need extra params

    # Fetch data
    data = _fetch_alphavantage(params)

    if 'error' in data:
        return [], [], {'error': data['error']}

    # Parse based on function type
    if function == 'CURRENCY_EXCHANGE_RATE':
        # Real-time quote, not time series
        rate_data = data.get('Realtime Currency Exchange Rate', {})
        if rate_data:
            rate = rate_data.get('5. Exchange Rate')
            date = rate_data.get('6. Last Refreshed', datetime.now().strftime('%Y-%m-%d'))
            if rate:
                dates = [date[:10]]  # Trim to date only
                values = [float(rate)]
            else:
                return [], [], {'error': 'No exchange rate data'}
        else:
            return [], [], {'error': 'No exchange rate data'}
    else:
        dates, values = _parse_time_series(data)

    if not dates:
        return [], [], {'error': 'No data returned from Alpha Vantage'}

    info = {
        'id': series_key,
        'title': series_info['name'],
        'description': series_info['description'],
        'units': series_info['units'],
        'frequency': series_info['frequency'],
        'source': 'Alpha Vantage',
        'measure_type': series_info['measure_type'],
        'change_type': series_info['change_type'],
        'fred_equivalent': series_info.get('fred_equivalent'),
    }

    return dates, values, info


def get_stock_price(symbol: str) -> tuple:
    """
    Fetch daily stock price for any symbol.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')

    Returns:
        (dates, values, info) tuple
    """
    params = {
        'function': 'TIME_SERIES_DAILY',
        'symbol': symbol.upper(),
        'outputsize': 'compact',  # 'full' requires premium
    }

    data = _fetch_alphavantage(params)

    if 'error' in data:
        return [], [], {'error': data['error']}

    dates, values = _parse_time_series(data)

    if not dates:
        return [], [], {'error': f'No data for symbol {symbol}'}

    info = {
        'id': f'av_stock_{symbol.lower()}',
        'title': f'{symbol.upper()} Stock Price',
        'description': f'Daily closing price for {symbol.upper()}',
        'units': 'dollars',
        'frequency': 'daily',
        'source': 'Alpha Vantage',
        'measure_type': 'nominal',
        'change_type': 'level',
    }

    return dates, values, info


def get_company_fundamentals(symbol: str) -> dict:
    """
    Fetch company fundamentals including P/E ratio, market cap, etc.

    Uses Alpha Vantage OVERVIEW endpoint to get valuation metrics.
    Free tier: 25 requests/day.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'SPY')

    Returns:
        Dict with fundamental data:
        - pe_ratio: Trailing P/E ratio
        - forward_pe: Forward P/E ratio
        - peg_ratio: P/E to growth ratio
        - price_to_book: Price to book value
        - price_to_sales: Price to sales ratio
        - eps: Earnings per share (TTM)
        - market_cap: Market capitalization
        - beta: Stock beta
        - 52_week_high/low: 52-week range
        - dividend_yield: Dividend yield %
        - profit_margin: Profit margin %
    """
    params = {
        'function': 'OVERVIEW',
        'symbol': symbol.upper(),
    }

    data = _fetch_alphavantage(params)

    if 'error' in data or not data:
        return {'error': f'No fundamentals data for {symbol}'}

    # Alpha Vantage returns "None" as string for missing values
    def safe_float(val):
        if val is None or val == 'None' or val == '-':
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    fundamentals = {
        'symbol': data.get('Symbol', symbol.upper()),
        'name': data.get('Name', ''),
        'description': data.get('Description', ''),
        'sector': data.get('Sector', ''),
        'industry': data.get('Industry', ''),

        # Valuation metrics
        'pe_ratio': safe_float(data.get('TrailingPE')),
        'forward_pe': safe_float(data.get('ForwardPE')),
        'peg_ratio': safe_float(data.get('PEGRatio')),
        'price_to_book': safe_float(data.get('PriceToBookRatio')),
        'price_to_sales': safe_float(data.get('PriceToSalesRatioTTM')),
        'ev_to_ebitda': safe_float(data.get('EVToEBITDA')),

        # Earnings & profitability
        'eps': safe_float(data.get('EPS')),
        'profit_margin': safe_float(data.get('ProfitMargin')),
        'operating_margin': safe_float(data.get('OperatingMarginTTM')),
        'return_on_equity': safe_float(data.get('ReturnOnEquityTTM')),
        'return_on_assets': safe_float(data.get('ReturnOnAssetsTTM')),

        # Market data
        'market_cap': safe_float(data.get('MarketCapitalization')),
        'beta': safe_float(data.get('Beta')),
        '52_week_high': safe_float(data.get('52WeekHigh')),
        '52_week_low': safe_float(data.get('52WeekLow')),

        # Dividends
        'dividend_yield': safe_float(data.get('DividendYield')),
        'dividend_per_share': safe_float(data.get('DividendPerShare')),

        # Growth
        'revenue_growth': safe_float(data.get('QuarterlyRevenueGrowthYOY')),
        'earnings_growth': safe_float(data.get('QuarterlyEarningsGrowthYOY')),

        # Analyst estimates
        'analyst_target_price': safe_float(data.get('AnalystTargetPrice')),
    }

    return fundamentals


def get_market_pe_summary() -> dict:
    """
    Get P/E ratio summary for major market indices/ETFs.

    Fetches fundamentals for SPY, QQQ, and key Mag7 stocks to provide
    market valuation context for bubble/valuation questions.

    Returns:
        Dict with market valuation summary
    """
    symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN']
    results = {}

    for symbol in symbols:
        fundamentals = get_company_fundamentals(symbol)
        if 'error' not in fundamentals:
            results[symbol] = {
                'name': fundamentals.get('name', symbol),
                'pe_ratio': fundamentals.get('pe_ratio'),
                'forward_pe': fundamentals.get('forward_pe'),
                'peg_ratio': fundamentals.get('peg_ratio'),
                'market_cap': fundamentals.get('market_cap'),
            }

    # Calculate averages for Mag7
    mag7_pes = [r['pe_ratio'] for s, r in results.items()
                if s not in ['SPY', 'QQQ'] and r.get('pe_ratio')]
    mag7_avg_pe = sum(mag7_pes) / len(mag7_pes) if mag7_pes else None

    return {
        'spy': results.get('SPY', {}),
        'qqq': results.get('QQQ', {}),
        'mag7_stocks': {k: v for k, v in results.items() if k not in ['SPY', 'QQQ']},
        'mag7_avg_pe': mag7_avg_pe,
        'timestamp': datetime.now().isoformat(),
    }


def search_alphavantage_series(query: str) -> list:
    """
    Search for Alpha Vantage series matching a query.

    Returns list of matching series keys.
    """
    query_lower = query.lower()
    matches = []

    for key, info in ALPHAVANTAGE_SERIES.items():
        searchable = (
            info['name'].lower() + ' ' +
            info.get('description', '').lower() + ' ' +
            ' '.join(info.get('keywords', []))
        )

        score = 0
        for word in query_lower.split():
            if word in searchable:
                score += 1

        if score > 0:
            matches.append((key, score, info['name']))

    matches.sort(key=lambda x: -x[1])
    return [m[0] for m in matches]


def get_available_series() -> dict:
    """Return all available Alpha Vantage series for catalog display."""
    return ALPHAVANTAGE_SERIES.copy()


def check_api_key() -> bool:
    """Check if Alpha Vantage API key is configured."""
    return bool(ALPHAVANTAGE_API_KEY)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("Testing Alpha Vantage data fetch...")
    print(f"API Key configured: {check_api_key()}")

    if not check_api_key():
        print("\nTo test, set ALPHAVANTAGE_API_KEY environment variable.")
        print("Get a free key at: https://www.alphavantage.co/support/#api-key")
    else:
        # Test SPY (S&P 500 ETF)
        print("\n1. Testing SPY (S&P 500 ETF):")
        dates, values, info = get_alphavantage_series('av_spy')
        if dates:
            print(f"   Got {len(dates)} observations")
            print(f"   Latest: {dates[-1]} = ${values[-1]:.2f}")
        else:
            print(f"   Error: {info.get('error', 'Unknown error')}")

        # Test Treasury yield
        print("\n2. Testing 10-Year Treasury Yield:")
        dates, values, info = get_alphavantage_series('av_treasury_10y')
        if dates:
            print(f"   Got {len(dates)} observations")
            print(f"   Latest: {dates[-1]} = {values[-1]:.2f}%")
        else:
            print(f"   Error: {info.get('error', 'Unknown error')}")

        # Test unemployment
        print("\n3. Testing Unemployment Rate:")
        dates, values, info = get_alphavantage_series('av_unemployment')
        if dates:
            print(f"   Got {len(dates)} observations")
            print(f"   Latest: {dates[-1]} = {values[-1]:.1f}%")
        else:
            print(f"   Error: {info.get('error', 'Unknown error')}")

        # Test crude oil
        print("\n4. Testing WTI Crude Oil:")
        dates, values, info = get_alphavantage_series('av_crude_oil')
        if dates:
            print(f"   Got {len(dates)} observations")
            print(f"   Latest: {dates[-1]} = ${values[-1]:.2f}/barrel")
        else:
            print(f"   Error: {info.get('error', 'Unknown error')}")

        # Test search
        print("\n5. Testing search for 'treasury yield':")
        matches = search_alphavantage_series("treasury yield")
        print(f"   Matches: {matches}")

        # Test individual stock
        print("\n6. Testing individual stock (AAPL):")
        dates, values, info = get_stock_price('AAPL')
        if dates:
            print(f"   Got {len(dates)} observations")
            print(f"   Latest: {dates[-1]} = ${values[-1]:.2f}")
        else:
            print(f"   Error: {info.get('error', 'Unknown error')}")


# =============================================================================
# NARRATIVE SYNTHESIS (Economist-style interpretation)
# =============================================================================

def synthesize_market_narrative(
    spy_price: Optional[float] = None,
    spy_change_pct: Optional[float] = None,
    vix_level: Optional[float] = None,
    treasury_10y: Optional[float] = None,
    treasury_2y: Optional[float] = None,
    dollar_index: Optional[float] = None,
    dollar_change_pct: Optional[float] = None,
) -> Optional[str]:
    """
    Synthesize financial market data into a coherent narrative paragraph.

    Explains what market signals mean for the economy and Fed policy.

    Args:
        spy_price: S&P 500 (SPY ETF) price level
        spy_change_pct: S&P 500 year-to-date or recent change (%)
        vix_level: VIX volatility index level
        treasury_10y: 10-year Treasury yield (%)
        treasury_2y: 2-year Treasury yield (%)
        dollar_index: Dollar index level or value
        dollar_change_pct: Dollar change (%)

    Returns:
        Human-readable narrative about financial market conditions
    """
    parts = []

    # Stock market sentiment
    if spy_change_pct is not None:
        if spy_change_pct > 15:
            parts.append(
                f"Stocks are up {spy_change_pct:.0f}%—a strong showing that reflects optimism about "
                "earnings growth and a soft landing. Elevated valuations require the economy to keep delivering."
            )
        elif spy_change_pct > 5:
            parts.append(
                f"Equities are up {spy_change_pct:.0f}%, suggesting investors see a healthy economic backdrop. "
                "Markets are pricing in continued growth without a recession."
            )
        elif spy_change_pct > -5:
            parts.append(
                f"Stocks are roughly flat ({spy_change_pct:+.1f}%), reflecting uncertainty about "
                "the path of interest rates and economic growth."
            )
        else:
            parts.append(
                f"Equities have fallen {abs(spy_change_pct):.0f}%, signaling growing concern about "
                "either recession risk, persistently high rates, or both."
            )

    # VIX volatility
    if vix_level is not None:
        if vix_level < 15:
            parts.append(
                f"The VIX at {vix_level:.0f} shows complacency—volatility is subdued and investors "
                "aren't hedging against downside risk. Low VIX can precede surprises."
            )
        elif vix_level < 20:
            parts.append(
                f"The VIX around {vix_level:.0f} reflects normal market conditions—"
                "neither excessive fear nor dangerous complacency."
            )
        elif vix_level < 30:
            parts.append(
                f"Elevated VIX at {vix_level:.0f} signals heightened uncertainty. "
                "Investors are paying up for downside protection, suggesting nervousness about near-term risks."
            )
        else:
            parts.append(
                f"The VIX at {vix_level:.0f} indicates significant market stress. "
                "Readings above 30 typically accompany sharp selloffs or crisis periods."
            )

    # Yield curve analysis
    if treasury_10y is not None and treasury_2y is not None:
        spread_bp = (treasury_10y - treasury_2y) * 100
        if spread_bp < -50:
            parts.append(
                f"The yield curve is deeply inverted ({spread_bp:.0f}bp), a classic recession signal. "
                "However, this indicator has been flashing for over a year without a downturn materializing—"
                "the 'soft landing' scenario remains in play."
            )
        elif spread_bp < 0:
            parts.append(
                f"The yield curve is mildly inverted ({spread_bp:.0f}bp). "
                "Markets expect the Fed to cut rates as growth slows, pushing short rates down over time."
            )
        elif spread_bp < 50:
            parts.append(
                f"The yield curve is roughly flat (+{spread_bp:.0f}bp), "
                "suggesting the Fed is near the end of its tightening cycle."
            )
        else:
            parts.append(
                f"A positively sloped curve (+{spread_bp:.0f}bp) is normal—"
                "investors demand more yield for locking up money longer."
            )
    elif treasury_10y is not None:
        if treasury_10y > 5:
            parts.append(
                f"The 10-year yield at {treasury_10y:.2f}% is the highest in over 15 years, "
                "raising borrowing costs for mortgages, corporate debt, and government spending. "
                "This level puts pressure on valuations and housing affordability."
            )
        elif treasury_10y > 4:
            parts.append(
                f"Treasury yields at {treasury_10y:.2f}% reflect a higher-for-longer rate environment. "
                "Bonds now offer real competition to stocks for the first time in years."
            )
        elif treasury_10y > 3:
            parts.append(
                f"The 10-year at {treasury_10y:.2f}% is normalized after years near zero. "
                "This is a 'return to normal' rather than tight conditions by historical standards."
            )

    # Dollar strength
    if dollar_change_pct is not None:
        if dollar_change_pct > 5:
            parts.append(
                f"The dollar has strengthened {dollar_change_pct:.0f}%, making US exports less competitive "
                "but helping contain import price inflation. A strong dollar also tightens financial conditions globally."
            )
        elif dollar_change_pct < -5:
            parts.append(
                f"The dollar has weakened {abs(dollar_change_pct):.0f}%, easing conditions for US exporters "
                "but adding modestly to import price pressures."
            )

    if not parts:
        return None

    return " ".join(parts)


def get_market_narrative() -> Optional[str]:
    """
    Convenience function to fetch current Alpha Vantage data and synthesize narrative.

    Requires ALPHAVANTAGE_API_KEY to be set.

    Returns:
        Synthesized narrative about current market conditions, or None on error.
    """
    if not check_api_key():
        return None

    # Fetch current data
    _, spy_values, _ = get_alphavantage_series('av_spy')
    _, treasury_10y_values, _ = get_alphavantage_series('av_treasury_10y')
    _, treasury_2y_values, _ = get_alphavantage_series('av_treasury_2y')

    # Calculate YTD change for S&P
    spy_change_pct = None
    if spy_values and len(spy_values) > 20:
        # Approximate YTD by looking at ~250 trading days ago or start of data
        start_idx = max(0, len(spy_values) - 252)  # Roughly 1 year
        spy_change_pct = ((spy_values[-1] / spy_values[start_idx]) - 1) * 100

    # Get latest values
    treasury_10y = treasury_10y_values[-1] if treasury_10y_values else None
    treasury_2y = treasury_2y_values[-1] if treasury_2y_values else None

    return synthesize_market_narrative(
        spy_change_pct=spy_change_pct,
        treasury_10y=treasury_10y,
        treasury_2y=treasury_2y,
    )
