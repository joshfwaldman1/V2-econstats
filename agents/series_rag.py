#!/usr/bin/env python3
"""
RAG-based FRED series retrieval.

Architecture:
1. Embed descriptions of FRED series
2. User query → embed → find similar series via cosine similarity
3. LLM picks best 2-4 from candidates

This approach reduces prompt complexity and lets the LLM focus on
selection rather than recall.
"""

import json
import os
import numpy as np
from pathlib import Path
from urllib.request import urlopen, Request
from typing import List, Dict, Optional, Tuple

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', os.environ.get('GOOGLE_API_KEY', ''))

# =============================================================================
# FRED SERIES CATALOG
# Curated list of important series with semantic descriptions
# =============================================================================

FRED_SERIES_CATALOG = [
    # === EMPLOYMENT - GENERAL ===
    {"id": "PAYEMS", "name": "Total Nonfarm Payrolls",
     "description": "Total number of jobs in the US economy excluding farm workers. The headline jobs number reported monthly. Shows how many jobs were added or lost."},
    {"id": "UNRATE", "name": "Unemployment Rate (U-3)",
     "description": "Percentage of the labor force that is unemployed and actively seeking work. The headline unemployment rate."},
    {"id": "U6RATE", "name": "Unemployment Rate (U-6)",
     "description": "Broader unemployment rate including discouraged workers and those working part-time for economic reasons."},
    {"id": "CIVPART", "name": "Labor Force Participation Rate",
     "description": "Percentage of working-age population either employed or actively looking for work."},
    {"id": "LNS12300060", "name": "Prime-Age Employment-Population Ratio",
     "description": "Percentage of people aged 25-54 who are employed. Best measure of labor market health, avoids retirement effects."},
    {"id": "JTSJOL", "name": "Job Openings (JOLTS)",
     "description": "Number of job openings available. Measures labor demand and how many positions employers are trying to fill."},
    {"id": "JTSQUR", "name": "Quits Rate",
     "description": "Rate at which workers voluntarily quit their jobs. High quits signal worker confidence in finding new jobs."},
    {"id": "ICSA", "name": "Initial Jobless Claims",
     "description": "Weekly count of new unemployment insurance claims. Most timely indicator of layoffs and labor market stress."},
    {"id": "CCSA", "name": "Continuing Jobless Claims",
     "description": "Number of people continuing to receive unemployment benefits. Shows how long people stay unemployed."},

    # === EMPLOYMENT - BY GENDER ===
    {"id": "LNS14000001", "name": "Unemployment Rate - Men",
     "description": "Unemployment rate for men. Male-specific labor market indicator."},
    {"id": "LNS14000002", "name": "Unemployment Rate - Women",
     "description": "Unemployment rate for women. Female-specific labor market indicator."},
    {"id": "LNS12300061", "name": "Prime-Age Employment Ratio - Men",
     "description": "Employment-population ratio for men aged 25-54. Best measure of men's labor market health."},
    {"id": "LNS12300062", "name": "Prime-Age Employment Ratio - Women",
     "description": "Employment-population ratio for women aged 25-54. Best measure of women's labor market health."},
    {"id": "LNS11300001", "name": "Labor Force Participation - Men",
     "description": "Labor force participation rate for men. Share of men working or looking for work."},
    {"id": "LNS11300002", "name": "Labor Force Participation - Women",
     "description": "Labor force participation rate for women. Share of women working or looking for work."},

    # === EMPLOYMENT - BY RACE ===
    {"id": "LNS14000003", "name": "Unemployment Rate - White",
     "description": "Unemployment rate for White workers. White-specific labor market indicator."},
    {"id": "LNS14000006", "name": "Unemployment Rate - Black",
     "description": "Unemployment rate for Black or African American workers. Black-specific labor market indicator."},
    {"id": "LNS14000009", "name": "Unemployment Rate - Hispanic",
     "description": "Unemployment rate for Hispanic or Latino workers. Hispanic-specific labor market indicator."},
    {"id": "LNS14032183", "name": "Unemployment Rate - Asian",
     "description": "Unemployment rate for Asian workers. Asian-specific labor market indicator."},

    # === EMPLOYMENT - IMMIGRANTS / FOREIGN-BORN ===
    {"id": "LNU04073395", "name": "Unemployment Rate - Foreign Born",
     "description": "Unemployment rate for foreign-born workers, immigrants. Immigrant-specific labor market indicator."},
    {"id": "LNU02073395", "name": "Employment Level - Foreign Born",
     "description": "Number of employed foreign-born workers, immigrants. Total immigrant employment."},
    {"id": "LNU01373395", "name": "Labor Force - Foreign Born",
     "description": "Foreign-born labor force, immigrants in workforce. Total immigrants working or seeking work."},
    {"id": "LNU04073413", "name": "Unemployment Rate - Native Born",
     "description": "Unemployment rate for native-born workers. US-born labor market indicator for comparison with immigrants."},
    {"id": "LNU02073413", "name": "Employment Level - Native Born",
     "description": "Number of employed native-born workers. US-born employment for comparison."},

    # === EMPLOYMENT - BY AGE ===
    {"id": "LNS14000012", "name": "Unemployment Rate - 16-19 years",
     "description": "Unemployment rate for teenagers aged 16-19. Youth labor market indicator."},
    {"id": "LNS14000036", "name": "Unemployment Rate - 20-24 years",
     "description": "Unemployment rate for young adults aged 20-24. Young worker labor market."},
    {"id": "LNS14000089", "name": "Unemployment Rate - 25-54 years",
     "description": "Unemployment rate for prime-age workers 25-54. Core working-age labor market."},
    {"id": "LNS14000091", "name": "Unemployment Rate - 55 and over",
     "description": "Unemployment rate for older workers 55+. Older worker labor market indicator."},

    # ==========================================================================
    # INDUSTRY-SPECIFIC EMPLOYMENT SERIES (BLS Current Employment Statistics)
    # ==========================================================================
    # These are the major supersector and detailed industry employment series
    # from the BLS Current Employment Statistics (CES) survey.
    # Optimized for semantic search queries like "how is the tech sector doing?"
    # "fintech companies", "banking industry", "healthcare workers", etc.

    # --- SUPERSECTOR EMPLOYMENT (Major Industry Groups) ---

    {"id": "MANEMP", "name": "Manufacturing Employment",
     "description": "Total employment in manufacturing sector. Factory jobs, industrial employment, manufacturing payrolls. Includes durable goods (machinery, computers, vehicles, aerospace, appliances, furniture) and nondurable goods (food processing, chemicals, textiles, pharmaceuticals, plastics). Key indicator for industrial economy health, trade policy impacts, automation trends, reshoring, onshoring. Manufacturing sector jobs, factory workers, production jobs, industrial jobs, blue collar manufacturing, made in USA, American manufacturing, plant workers."},

    {"id": "USCONS", "name": "Construction Employment",
     "description": "Total employment in construction sector. Building jobs, construction workers, contractors, builders, tradespeople. Includes residential construction (homebuilding, home improvement, remodeling), commercial construction (offices, retail, warehouses, data centers), heavy/civil construction (roads, bridges, highways, infrastructure), and specialty trades (electricians, plumbers, HVAC, carpenters, roofers, masons). Key indicator for housing market, infrastructure spending, real estate development. Construction industry jobs, hard hats, building trades, skilled trades."},

    {"id": "USPRIV", "name": "Total Private Sector Employment",
     "description": "Total private sector employment, all private industries combined. Excludes government workers at all levels (federal, state, local). This is the broadest measure of private employment in the US economy. Private payrolls, private sector jobs, non-government employment, private industry employment, business sector jobs, private economy, corporate America employment, private businesses."},

    {"id": "USGOVT", "name": "Government Employment",
     "description": "Total government employment at all levels - federal, state, and local. Federal civilian workers (excludes military), state government employees, local government workers including teachers, police officers, firefighters, sanitation workers, DMV, postal workers. Public sector jobs, government payrolls, civil service, public employees, government workers, bureaucrats, municipal workers, city workers, county workers."},

    {"id": "USMINE", "name": "Mining and Logging Employment",
     "description": "Employment in mining and logging sector. Oil and gas extraction workers, coal mining, metal ore mining (copper, gold, iron), quarrying, stone/sand/gravel, logging, timber harvesting, forestry. Energy sector employment, natural resources, extractive industries. Includes oil rigs, drilling, fracking, shale jobs, offshore drilling, pipeline. Mining industry jobs, oil patch jobs, energy extraction, natural resource workers, roughnecks, drillers, wildcatters."},

    {"id": "USTPU", "name": "Trade Transportation and Utilities Employment",
     "description": "Employment in trade, transportation, and utilities supersector. Includes wholesale trade (distribution, warehousing, B2B sales), retail trade (stores, shops, e-commerce), transportation (trucking, airlines, railroads, shipping, ports, delivery services like UPS FedEx), warehousing (logistics, fulfillment centers, Amazon warehouses), and utilities (electric power, natural gas, water). Supply chain jobs, logistics employment, retail workers, warehouse workers, truck drivers, delivery drivers, distribution."},

    {"id": "USINFO", "name": "Information Sector Employment",
     "description": "Employment in information sector. Technology jobs, tech workers, software companies, IT employment, digital economy. Includes telecommunications (phone, internet, cable, wireless carriers like Verizon AT&T), broadcasting (TV, radio, streaming services like Netflix), publishing (newspapers, books, digital media, software publishers), motion pictures/film, data processing, web hosting, cloud computing (AWS, Azure, Google Cloud), video games. Tech sector jobs, technology industry, media jobs, Silicon Valley, fintech companies, Big Tech, FAANG, startups, software engineers, developers, programmers, IT workers."},

    {"id": "USFIRE", "name": "Financial Activities Employment",
     "description": "Employment in finance, insurance, and real estate (FIRE sector). Banking jobs, bankers, financial services workers, Wall Street, insurance industry, real estate agents, property management. Includes commercial banking (JPMorgan, Bank of America, Wells Fargo), investment banking (Goldman Sachs, Morgan Stanley), credit unions, hedge funds, private equity, asset management, insurance carriers and agents (State Farm, Allstate, MetLife), real estate brokerages (Redfin, Zillow, Compass), REITs, mortgage companies, fintech (PayPal, Square, Stripe). Financial sector jobs, banking industry, insurance jobs, real estate employment, lenders, underwriters, loan officers, financial advisors."},

    {"id": "USPBS", "name": "Professional and Business Services Employment",
     "description": "Employment in professional and business services. White collar jobs, knowledge workers, corporate services. Includes consulting firms (McKinsey, BCG, Deloitte, Accenture), legal services (law firms, lawyers, attorneys), accounting firms (Big 4: PwC, EY, KPMG, Deloitte), management consulting, advertising and marketing agencies, computer systems design, IT consulting, architecture, engineering firms, scientific research, R&D, staffing agencies (temp agencies like Robert Half, Manpower), administrative services, HR outsourcing, call centers. Professional services jobs, business services, consultants, lawyers, accountants, office jobs."},

    {"id": "USEHS", "name": "Education and Health Services Employment",
     "description": "Employment in education and health services. Healthcare workers, nurses, doctors, physicians, hospital employment, medical jobs. Includes hospitals (HCA, Kaiser), nursing homes, assisted living, clinics, outpatient care, home health aides, medical technicians, pharmacies, dental offices, physical therapy. Education workers, teachers, professors, school administrators, universities, colleges, K-12 schools, private schools, tutoring. Healthcare industry jobs, healthcare sector, medical employment, nursing jobs, hospital workers, eldercare, senior care, childcare, daycare workers, medical field, health sector."},

    {"id": "USLAH", "name": "Leisure and Hospitality Employment",
     "description": "Employment in leisure and hospitality sector. Restaurant workers, food service, hotel staff, hospitality industry, tourism. Includes restaurants (McDonald's, Starbucks, Chipotle), bars, fast food, quick service (QSR), full-service dining, hotels and motels (Marriott, Hilton, Hyatt), resorts, casinos, gaming, amusement parks (Disney, Universal), theme parks, recreation, arts, performing arts, museums, sports, fitness centers, gyms, spas, travel and tourism. Restaurant employment, hospitality jobs, waiters, waitresses, servers, bartenders, chefs, cooks, hotel housekeeping, front desk, tourism industry, entertainment jobs, service industry, vacation jobs."},

    {"id": "USSERV", "name": "Other Services Employment",
     "description": "Employment in other services sector (excluding public administration). Includes repair and maintenance (auto repair shops, mechanics, appliance repair, electronics repair, HVAC service), personal care services (hair salons, barbershops, beauty salons, spas, nail salons, dry cleaners, laundry, tailors), religious organizations (churches, temples, synagogues), civic and social organizations (nonprofits, charities, unions, political organizations), private households (domestic workers, housekeepers, nannies, personal assistants). Personal services, automotive services, pet grooming, veterinary, funeral services."},

    # --- DETAILED INDUSTRY EMPLOYMENT (Specific Subsectors) ---

    {"id": "CES4300000001", "name": "Retail Trade Employment",
     "description": "Total employment in retail trade industry specifically. Store workers, retail jobs, shopping, sales associates, cashiers. Includes department stores (Macy's, Nordstrom), grocery stores and supermarkets (Kroger, Safeway, Whole Foods), apparel and clothing stores (Gap, H&M), electronics stores (Best Buy), home improvement (Home Depot, Lowes), auto dealers, gas stations, convenience stores, pharmacies (CVS, Walgreens), sporting goods, furniture stores, e-commerce fulfillment. Retail sector jobs, retail industry, store employment, retail workers, shop workers, retail sales, brick and mortar, Amazon effect, mall jobs, retail apocalypse."},

    {"id": "CES6500000001", "name": "Financial Activities Employment (Detailed)",
     "description": "Detailed employment in financial activities sector. More granular view than USFIRE supersector. Banking jobs, insurance employment, real estate workers. Includes depository credit institutions (commercial banks, savings banks, credit unions), nondepository credit (mortgage companies, finance companies, credit card companies, consumer lending), securities and commodities (brokerages, investment banks, stock exchanges, trading), insurance carriers and agencies, funds/trusts (mutual funds, pension funds, hedge funds), real estate operations, rental and leasing. Wall Street employment, financial industry jobs, FIRE sector."},

    {"id": "CES6562000001", "name": "Credit Intermediation and Related Activities Employment",
     "description": "Employment in credit intermediation - the banking and lending industry specifically. Commercial banks (Chase, BofA, Citi, Wells), savings institutions, credit unions, mortgage banking and brokers, credit card companies (Visa, Mastercard, Amex), consumer lending, sales financing, loan officers, bank tellers, branch managers, loan processors, underwriters. Banking sector employment, banking jobs, lending industry jobs, financial institutions employment, bank workers, credit industry, commercial banking, community banks, regional banks."},

    {"id": "CES5000000001", "name": "Information Sector Employment (Detailed)",
     "description": "Detailed information sector employment breakdown. Tech jobs, media jobs. Includes publishing industries (newspapers, periodicals, books, software publishers like Microsoft, Adobe, Salesforce), motion picture and sound recording (film studios, music labels, streaming), broadcasting (radio, TV stations, cable networks), telecommunications (wired carriers, wireless/cellular, satellite, internet service providers), data processing and hosting (cloud computing, data centers, web hosting), internet publishing and web search portals (Google, Meta/Facebook, Twitter). Tech employment, digital media, telecom jobs."},

    {"id": "CES7000000001", "name": "Leisure and Hospitality Employment (Detailed)",
     "description": "Detailed leisure and hospitality employment. Arts, entertainment, and recreation plus accommodation and food services. Performing arts and spectator sports (theaters, concerts, sports teams, stadiums), museums and historical sites, amusement parks and arcades, gambling and casinos, fitness and recreation (gyms, golf courses, ski resorts), hotels and motels, RV parks, rooming houses, full-service restaurants, limited-service restaurants (fast food, fast casual), cafeterias, caterers, bars and drinking places. Detailed restaurant jobs, hotel employment, entertainment industry."},

    {"id": "CES4142000001", "name": "Wholesale Trade Employment",
     "description": "Employment in wholesale trade - distribution and B2B sales, the middleman between manufacturers and retailers. Durable goods wholesalers (machinery, computers, electronics, automotive parts, furniture), nondurable goods wholesalers (groceries and food, apparel, chemicals, pharmaceuticals, paper). Distribution centers, wholesale distributors, B2B sales representatives, supply chain, distribution industry, warehouse operations, inventory management."},

    {"id": "CES4244100001", "name": "Grocery Store Employment",
     "description": "Employment in grocery stores and supermarkets specifically. Grocery workers, supermarket employees, food retail. Includes large grocery chains (Kroger, Safeway, Albertsons, Publix, H-E-B), warehouse clubs (Costco, Sam's Club, BJ's), specialty food stores, organic grocers (Whole Foods, Trader Joe's). Grocery industry jobs, food retail employment, essential workers, front-line retail, checkout workers, stock clerks, deli workers, bakery workers, produce workers."},

    {"id": "CES7072200001", "name": "Food Services and Drinking Places Employment",
     "description": "Employment in restaurants and bars specifically. Full-service restaurants (sit-down dining, casual dining like Applebee's, Olive Garden, fine dining), limited-service restaurants (fast food like McDonald's, Wendy's, fast casual like Chipotle, Panera), cafeterias and buffets, snack and beverage bars (Starbucks, Dunkin), caterers and food trucks, bars, taverns, and nightclubs. Restaurant industry employment, food service workers, waiters/waitresses, servers, cooks, chefs, bartenders, fast food workers, QSR employment, dining industry, hospitality."},

    {"id": "CES3133440001", "name": "Semiconductor Manufacturing Employment",
     "description": "Employment in semiconductor and electronic component manufacturing. Chip makers, chipmakers, semiconductor fabrication, electronics manufacturing, integrated circuits. Companies like Intel, TSMC, Samsung, Micron, Nvidia, AMD. CHIPS Act, semiconductor supply chain, chip shortage, fab workers, cleanroom technicians. Tech hardware manufacturing, chip production, microprocessor manufacturing, memory chips, semiconductors jobs."},

    # === WAGES AND EARNINGS ===
    {"id": "CES0500000003", "name": "Average Hourly Earnings",
     "description": "Average hourly earnings for all private employees. Wage growth, pay levels."},
    {"id": "AHETPI", "name": "Average Hourly Earnings - Production Workers",
     "description": "Average hourly earnings for production and nonsupervisory workers. Blue-collar wages."},
    {"id": "LES1252881600Q", "name": "Median Weekly Earnings",
     "description": "Real median weekly earnings for full-time workers. Inflation-adjusted middle-class wages."},
    {"id": "MEPAINUSA672N", "name": "Median Personal Income",
     "description": "Median personal income in the US. Middle-class income levels."},

    # === INFLATION AND PRICES ===
    {"id": "CPIAUCSL", "name": "Consumer Price Index (CPI)",
     "description": "Consumer price index for all urban consumers. Headline inflation, cost of living."},
    {"id": "CPILFESL", "name": "Core CPI",
     "description": "CPI excluding food and energy. Core inflation, underlying price pressures."},
    {"id": "PCEPI", "name": "PCE Price Index",
     "description": "Personal consumption expenditures price index. Fed's preferred inflation measure."},
    {"id": "PCEPILFE", "name": "Core PCE",
     "description": "Core PCE excluding food and energy. The Fed's 2% inflation target measure."},
    {"id": "CUSR0000SAH1", "name": "CPI - Shelter",
     "description": "Consumer price index for shelter - TOTAL HOUSING COSTS including rent and owners equivalent rent. Shelter inflation, housing CPI, housing costs inflation, is shelter inflation coming down, housing component of CPI. Shelter is ~35% of CPI and the stickiest component - key driver of core inflation. When people ask about housing inflation or rent inflation broadly, this is the comprehensive measure."},
    {"id": "CUSR0000SAF11", "name": "CPI - Food at Home",
     "description": "Consumer price index for groceries. Food prices, grocery inflation."},
    {"id": "CUSR0000SEFV", "name": "CPI - Food Away from Home",
     "description": "Consumer price index for restaurants and dining out. Restaurant prices, eating out costs."},
    {"id": "CUSR0000SETB01", "name": "CPI - Gasoline",
     "description": "Consumer price index for gasoline. Gas prices, fuel costs."},
    {"id": "GASREGW", "name": "Regular Gas Price",
     "description": "Average price of regular gasoline per gallon. Pump prices, fuel costs."},

    # === GDP AND ECONOMIC GROWTH ===
    {"id": "GDPC1", "name": "Real GDP",
     "description": "Real gross domestic product. Total economic output, size of the economy."},
    {"id": "A191RL1Q225SBEA", "name": "Real GDP Growth (Quarterly)",
     "description": "Quarterly GDP growth rate, annualized. Economic growth, expansion or contraction."},
    {"id": "A191RO1Q156NBEA", "name": "Real GDP Growth (Year-over-Year)",
     "description": "GDP growth compared to same quarter last year. Annual economic growth rate."},
    {"id": "INDPRO", "name": "Industrial Production Index",
     "description": "Industrial production index. Manufacturing output, factory production."},
    {"id": "TCU", "name": "Capacity Utilization",
     "description": "Total capacity utilization rate. How much of productive capacity is being used."},

    # === INTEREST RATES ===
    {"id": "FEDFUNDS", "name": "Federal Funds Rate",
     "description": "Federal funds effective rate. The Fed's policy interest rate, overnight lending rate."},
    {"id": "DGS10", "name": "10-Year Treasury Yield",
     "description": "10-year Treasury constant maturity rate. Long-term interest rates, bond yields."},
    {"id": "DGS2", "name": "2-Year Treasury Yield",
     "description": "2-year Treasury constant maturity rate. Short-term rates, Fed policy expectations."},
    {"id": "T10Y2Y", "name": "10Y-2Y Treasury Spread",
     "description": "Spread between 10-year and 2-year Treasury yields. Yield curve, recession indicator when inverted."},
    {"id": "MORTGAGE30US", "name": "30-Year Fixed Mortgage Rate",
     "description": "30-year fixed rate mortgage average from Freddie Mac Primary Mortgage Market Survey. The benchmark rate for US home loans. Critical for housing affordability - each 1% increase adds ~$200/month to typical payment. Fed policy directly impacts this rate."},
    {"id": "MORTGAGE15US", "name": "15-Year Mortgage Rate",
     "description": "15-year fixed mortgage rate. Shorter-term home loan rates."},

    # === FED PROJECTIONS (SEP - Summary of Economic Projections) ===
    {"id": "FEDTARMD", "name": "Fed Funds Rate Projection (Median)",
     "description": "FOMC median projection for federal funds rate. Fed dot plot, expected rate path."},
    {"id": "FEDTARMDLR", "name": "Fed Funds Rate Long-Run Projection",
     "description": "FOMC long-run median projection for federal funds rate. Neutral rate estimate, r-star."},
    {"id": "UNRATEMD", "name": "Unemployment Rate Projection (Median)",
     "description": "FOMC median projection for unemployment rate. Fed forecast for jobless rate."},
    {"id": "UNRATEMDLR", "name": "Unemployment Long-Run Projection",
     "description": "FOMC long-run median projection for unemployment. Natural rate of unemployment estimate, NAIRU."},
    {"id": "GDPC1MD", "name": "Real GDP Growth Projection (Median)",
     "description": "FOMC median projection for real GDP growth. Fed forecast for economic growth."},
    {"id": "GDPC1MDLR", "name": "Real GDP Long-Run Growth Projection",
     "description": "FOMC long-run median projection for real GDP growth. Potential growth rate estimate."},
    {"id": "PCECTPIMD", "name": "PCE Inflation Projection (Median)",
     "description": "FOMC median projection for PCE inflation. Fed forecast for headline inflation."},
    {"id": "PCECTPIMDLR", "name": "PCE Inflation Long-Run Projection",
     "description": "FOMC long-run median projection for PCE inflation. Inflation target (2%)."},
    {"id": "JCXFEMD", "name": "Core PCE Inflation Projection (Median)",
     "description": "FOMC median projection for core PCE inflation. Fed forecast for underlying inflation excluding food and energy."},
    {"id": "FEDTARCTL", "name": "Fed Funds Rate Projection (Central Tendency Low)",
     "description": "FOMC central tendency low for federal funds rate. Lower bound of middle participant projections."},
    {"id": "FEDTARCTH", "name": "Fed Funds Rate Projection (Central Tendency High)",
     "description": "FOMC central tendency high for federal funds rate. Upper bound of middle participant projections."},

    # === HOUSING ===
    {"id": "CSUSHPINSA", "name": "Case-Shiller Home Price Index",
     "description": "S&P/Case-Shiller national home price index. House prices, real estate values."},
    {"id": "MSPUS", "name": "Median Home Sales Price",
     "description": "Median sales price of houses sold. Typical home price, housing costs."},
    {"id": "HOUST", "name": "Housing Starts",
     "description": "New residential construction starts. Home building activity, new housing supply."},
    {"id": "PERMIT", "name": "Building Permits",
     "description": "New private housing units authorized by permits. Future construction pipeline."},
    {"id": "EXHOSLUSM495S", "name": "Existing Home Sales",
     "description": "Existing home sales. Housing market activity, home buying volume."},
    {"id": "NHSUSSPT", "name": "New Home Sales",
     "description": "New single-family home sales. New construction sales volume."},
    {"id": "RRVRUSQ156N", "name": "Rental Vacancy Rate",
     "description": "Rental vacancy rate. Empty rental units, rental market tightness."},

    # === CONSUMER ===
    {"id": "UMCSENT", "name": "Consumer Sentiment",
     "description": "University of Michigan consumer sentiment index. Consumer confidence, economic optimism."},
    {"id": "PCE", "name": "Personal Consumption Expenditures",
     "description": "Total personal consumption expenditures. Consumer spending, household purchases."},
    {"id": "RSAFS", "name": "Retail Sales",
     "description": "Advance retail sales. Consumer spending at stores, shopping activity."},
    {"id": "PSAVERT", "name": "Personal Saving Rate",
     "description": "Personal saving rate as percentage of income. How much households save."},
    {"id": "TOTALSL", "name": "Total Consumer Credit Outstanding",
     "description": "Total consumer credit outstanding, including revolving (credit cards) and non-revolving (auto, student loans). Key measure of household debt levels and consumer borrowing capacity. Indicates consumer financial health and spending power."},
    {"id": "DSPIC96", "name": "Real Disposable Income",
     "description": "Real disposable personal income. Inflation-adjusted income after taxes."},

    # === TRADE AND INTERNATIONAL ===
    {"id": "BOPGSTB", "name": "Trade Balance",
     "description": "US trade balance in goods and services. Exports minus imports, trade deficit."},
    {"id": "EXPGS", "name": "Exports",
     "description": "US exports of goods and services. What America sells abroad."},
    {"id": "IMPGS", "name": "Imports",
     "description": "US imports of goods and services. What America buys from abroad."},
    {"id": "DTWEXBGS", "name": "Dollar Index",
     "description": "Trade-weighted US dollar index. Dollar strength against trading partners."},

    # === FINANCIAL MARKETS ===
    {"id": "SP500", "name": "S&P 500",
     "description": "S&P 500 stock market index. Stock prices, equity market performance."},
    {"id": "NASDAQCOM", "name": "NASDAQ Composite",
     "description": "NASDAQ composite index. Tech stocks, technology sector performance."},
    {"id": "DJIA", "name": "Dow Jones Industrial Average",
     "description": "Dow Jones Industrial Average. Blue-chip stocks, industrial companies."},
    {"id": "VIXCLS", "name": "VIX Volatility Index",
     "description": "CBOE volatility index, the fear gauge. Market uncertainty, expected volatility."},

    # === CREDIT / BOND SPREADS ===
    {"id": "BAMLH0A0HYM2", "name": "High Yield Corporate Bond Spread",
     "description": "ICE BofA high yield spread over Treasuries. Credit risk, junk bond spreads, corporate distress."},

    # === RECESSION INDICATORS ===
    {"id": "SAHMREALTIME", "name": "Sahm Rule Recession Indicator",
     "description": "Sahm rule recession indicator. Signals recession when unemployment rises quickly."},
    {"id": "BBKMLEIX", "name": "Chicago Fed Leading Index",
     "description": "Brave-Butters-Kelley leading index. Forecasts future economic growth."},
    {"id": "USREC", "name": "NBER Recession Indicator",
     "description": "NBER recession indicator. Official recession dating, economic contractions."},
    {"id": "T10Y3M", "name": "10Y-3M Treasury Spread",
     "description": "Spread between 10-year Treasury and 3-month bill. Yield curve inversion, recession predictor."},

    # === COMMODITIES ===
    {"id": "DCOILWTICO", "name": "Crude Oil Price (WTI)",
     "description": "West Texas Intermediate crude oil price. Oil prices, energy costs."},
    {"id": "DCOILBRENTEU", "name": "Crude Oil Price (Brent)",
     "description": "Brent crude oil price. International oil benchmark."},
    {"id": "GOLDAMGBD228NLBM", "name": "Gold Price",
     "description": "Gold price per troy ounce. Gold prices, precious metals, safe haven."},

    # === GOVERNMENT AND DEBT ===
    {"id": "GFDEBTN", "name": "Federal Debt",
     "description": "Total federal government debt. National debt, government borrowing."},
    {"id": "FYFSD", "name": "Federal Surplus/Deficit",
     "description": "Federal government budget surplus or deficit. Government spending vs revenue."},
    {"id": "FGEXPND", "name": "Federal Government Spending",
     "description": "Total federal government expenditures. Government spending levels."},
    {"id": "FGRECPT", "name": "Federal Government Revenue",
     "description": "Total federal government receipts. Tax revenue, government income."},

    # === SMALL BUSINESS ===
    {"id": "NFIBOPTIMISM", "name": "NFIB Small Business Optimism Index",
     "description": "NFIB Small Business Optimism Index. Survey of small business owners covering hiring plans, capital spending, sales expectations, and economic outlook. Small businesses employ half of US workers - their sentiment predicts broader economic trends and is a leading indicator of hiring and investment."},
    {"id": "BUSLOANS", "name": "Commercial & Industrial Loans at Banks",
     "description": "Commercial and industrial loans at all commercial banks. Business lending from banks for working capital, equipment, and expansion. Key indicator of business credit conditions, corporate investment appetite, and bank willingness to lend to companies."},
    {"id": "DRTSCLCC", "name": "Bank Lending Standards - Credit Cards",
     "description": "Net percentage of banks tightening standards for credit card loans from Senior Loan Officer Survey. Positive values mean banks are tightening; rising values signal credit crunch for consumers. Leads credit card growth by 2-3 quarters."},

    # === SUPPLY CHAIN / LOGISTICS ===
    {"id": "RAILFRTINTERMODAL", "name": "Rail Freight Intermodal Traffic",
     "description": "Rail freight intermodal traffic. Shipping containers, supply chain activity."},
    {"id": "NAPMPI", "name": "ISM Manufacturing Prices Index",
     "description": "ISM manufacturing prices paid index. Input costs, supply chain pressures."},
    {"id": "NAPMPMD", "name": "ISM Manufacturing Supplier Deliveries",
     "description": "ISM manufacturing supplier deliveries index. Supply chain delays, bottlenecks."},
    {"id": "TSIFRGHT", "name": "Transportation Services Index - Freight",
     "description": "Transportation services index for freight. Shipping activity, logistics volume."},

    # === VETERANS EMPLOYMENT ===
    {"id": "LNS14049526", "name": "Unemployment Rate - Gulf War Era II Veterans",
     "description": "Unemployment rate for veterans who served since September 2001. Post-9/11 veterans' employment."},
    {"id": "LNU04049526", "name": "Unemployed Gulf War Era II Veterans",
     "description": "Number of unemployed veterans who served since September 2001. Veterans job seekers."},

    # === MONEY SUPPLY / MONETARY ===
    {"id": "M2SL", "name": "M2 Money Supply",
     "description": "M2 money supply. Money in circulation, cash and deposits."},
    {"id": "BOGMBASE", "name": "Monetary Base",
     "description": "St. Louis adjusted monetary base. Currency plus bank reserves."},
    {"id": "WALCL", "name": "Fed Balance Sheet",
     "description": "Federal Reserve total assets. Fed balance sheet size, quantitative easing."},

    # === AUTO / VEHICLES ===
    {"id": "TOTALSA", "name": "Total Vehicle Sales",
     "description": "Total vehicle sales. Car and truck sales, auto industry demand."},
    {"id": "ALTSALES", "name": "Light Vehicle Sales",
     "description": "Light vehicle sales - cars and light trucks. Consumer auto purchases."},

    # === ENERGY ===
    {"id": "IPG211111CS", "name": "Crude Oil Production Index",
     "description": "Industrial production: crude oil. US oil production, energy output."},
    {"id": "CLPR", "name": "Coal Production",
     "description": "US coal production. Mining output, fossil fuel production."},

    # === BUSINESS SURVEYS - ISM/PMI ===
    {"id": "NAPM", "name": "ISM Manufacturing PMI Composite",
     "description": "ISM Manufacturing Purchasing Managers Index composite. Key leading indicator of manufacturing sector health - readings above 50 indicate expansion, below 50 indicate contraction. Highly watched for early signals of economic turning points."},
    {"id": "NAPMNOI", "name": "ISM Manufacturing New Orders",
     "description": "ISM Manufacturing New Orders Index. Forward-looking component of PMI tracking incoming business - rising new orders signal future production increases and economic expansion. One of the most predictive PMI subcomponents."},
    {"id": "NAPMPRD", "name": "ISM Manufacturing Production Index",
     "description": "ISM Manufacturing Production Index. Measures current output levels in manufacturing. When combined with new orders, shows whether production is keeping pace with demand."},
    {"id": "NAPMEI", "name": "ISM Manufacturing Employment",
     "description": "ISM Manufacturing Employment Index. Leading indicator of manufacturing payrolls - factory hiring intentions ahead of official BLS data. Useful for forecasting manufacturing job growth."},
    {"id": "NMFBAI", "name": "ISM Non-Manufacturing Business Activity",
     "description": "ISM Non-Manufacturing Business Activity Index (Services PMI). Covers ~80% of US economy. Key indicator of service sector health - readings above 50 signal expansion. Critical for understanding broad economic conditions beyond manufacturing."},

    # === BUSINESS SURVEYS - CONFERENCE BOARD ===
    {"id": "CSCICP03USM665S", "name": "Consumer Confidence Index",
     "description": "Conference Board Consumer Confidence Index. Measures consumer optimism about economy and personal finances. Leading indicator of consumer spending - confident consumers spend more. Sharp drops often precede recessions."},
    {"id": "BSCICP03USM665S", "name": "Business Confidence Index",
     "description": "Conference Board Business Confidence Index. Measures CEO and business leader sentiment about economic conditions. Forward-looking indicator of business investment and hiring decisions."},
    {"id": "USSLIND", "name": "Leading Economic Index (LEI)",
     "description": "Conference Board Leading Economic Index. Composite of 10 leading indicators designed to forecast economic turning points. Three consecutive monthly declines historically signal recession risk. The gold standard for recession forecasting."},
    {"id": "RECPROUSM156N", "name": "Recession Probability Index",
     "description": "Smoothed US Recession Probabilities. Model-based estimate of probability the US is in recession. Combines multiple indicators to provide a single recession risk measure. Values above 50% strongly suggest recession."},

    # === BUSINESS SURVEYS - REGIONAL FED ===
    {"id": "GACDISA066MSFRBNY", "name": "NY Fed Empire State Manufacturing",
     "description": "NY Fed Empire State Manufacturing Survey. First regional manufacturing survey released each month - provides early read on factory sector. Covers NY, NJ, CT. Positive values indicate expansion."},
    {"id": "GACDFSA066MSFRBPHI", "name": "Philly Fed Manufacturing Index",
     "description": "Philadelphia Fed Manufacturing Business Outlook Survey. Closely watched regional indicator covering PA, NJ, DE. Often confirms or previews ISM Manufacturing. Positive values indicate expansion."},
    {"id": "TEXMFGPHIPERSINDX", "name": "Dallas Fed Manufacturing Index",
     "description": "Dallas Fed Texas Manufacturing Outlook Survey - Production Index. Key regional indicator for energy-heavy Texas manufacturing. Useful for understanding oil/gas sector business conditions. Positive values indicate expansion."},
    {"id": "RSXFS", "name": "Retail Sales Ex Food Services",
     "description": "Advance Retail Sales excluding Food Services. Cleaner measure of goods consumption excluding volatile restaurant spending. Proxy for underlying consumer demand strength. Key input to GDP nowcasts."},

    # === CREDIT AND LENDING - CONSUMER CREDIT ===
    {"id": "REVOLSL", "name": "Revolving Consumer Credit (Credit Cards)",
     "description": "Revolving consumer credit outstanding, primarily credit card debt. Indicates short-term borrowing and consumer spending patterns. High growth can signal consumer confidence or financial stress depending on context."},
    {"id": "NONREVSL", "name": "Non-Revolving Consumer Credit",
     "description": "Non-revolving consumer credit including auto loans and student loans. Longer-term consumer debt for major purchases like vehicles and education. Reflects household financial commitments and access to credit."},
    {"id": "DTCTHFNM", "name": "Credit Card Debt Outstanding",
     "description": "Total credit card debt held by consumers at finance companies. Direct measure of credit card balances and consumer revolving debt. Rising balances can indicate financial stress or increased spending power."},
    {"id": "MVLOAS", "name": "Motor Vehicle Loans Outstanding",
     "description": "Total motor vehicle loans outstanding at all lenders. Auto loan debt held by consumers. Key indicator of auto market health, consumer borrowing for vehicles, and household debt burden."},
    {"id": "SLOAS", "name": "Student Loans Outstanding",
     "description": "Total student loan debt outstanding owned by federal government and commercial entities. Measures educational debt burden on households. Critical for understanding millennial and Gen-Z financial health and spending constraints."},

    # === CREDIT AND LENDING - DELINQUENCIES ===
    {"id": "DRCCLACBS", "name": "Credit Card Delinquency Rate",
     "description": "Delinquency rate on credit card loans at commercial banks. Percentage of credit card debt 30+ days past due. Key indicator of consumer financial stress and credit risk. Rises sharply before and during recessions."},
    {"id": "DRSFRMACBS", "name": "Mortgage Delinquency Rate",
     "description": "Delinquency rate on single-family residential mortgages at commercial banks. Measures housing market stress and homeowner financial health. Critical indicator during housing downturns - spiked to 11% in 2010."},
    {"id": "DRALACBN", "name": "Auto Loan Delinquency Rate",
     "description": "Delinquency rate on auto loans at commercial banks. Measures auto loan defaults and consumer credit stress. Early warning indicator for consumer financial distress given auto loan prevalence."},
    {"id": "SUBLPDRCSC", "name": "Subprime Auto Loan Delinquency Rate",
     "description": "Subprime auto loan delinquency rate from NY Fed Consumer Credit Panel. Tracks 60+ day delinquencies among riskier borrowers. Leading indicator of broader consumer credit problems - often rises before prime delinquencies."},

    # === CREDIT AND LENDING - BANK LENDING ===
    {"id": "REALLN", "name": "Real Estate Loans at Commercial Banks",
     "description": "Real estate loans at all commercial banks. Total mortgage and commercial real estate lending by banks. Measures credit availability for property purchases, construction, and development."},
    {"id": "TOTCI", "name": "Total C&I Loans (Weekly)",
     "description": "Total commercial and industrial loans reported weekly at commercial banks. High-frequency measure of business lending trends. More timely than monthly data for tracking credit conditions in real-time."},
    {"id": "H8B1058NCBCMG", "name": "Consumer Loans at Commercial Banks",
     "description": "Consumer loans at all commercial banks. Total consumer lending including credit cards, auto loans, and personal loans. Measures bank exposure to consumer credit and household borrowing from banks."},

    # === CREDIT AND LENDING - LENDING STANDARDS (Senior Loan Officer Survey) ===
    {"id": "DRTSCIS", "name": "Bank Lending Standards - Small Business C&I",
     "description": "Net percentage of banks tightening standards for C&I loans to small firms from Senior Loan Officer Survey. Critical for small business access to capital. Tightening restricts hiring and investment by small businesses."},
    {"id": "DRTSCILM", "name": "Bank Lending Standards - Large/Medium C&I",
     "description": "Net percentage of banks tightening standards for C&I loans to large and medium firms. Corporate credit conditions from Senior Loan Officer Survey. Widespread tightening indicates risk aversion and can slow business investment."},

    # === CREDIT AND LENDING - MORTGAGE MARKET ===
    {"id": "WRMORTNS", "name": "Weekly Mortgage Applications Index",
     "description": "MBA weekly mortgage applications index, not seasonally adjusted. Tracks mortgage application volume for purchases and refinancing. Leading indicator of home sales activity and housing demand. Highly sensitive to rate changes."},

    # ==========================================================================
    # EXPANDED CATALOG: SECTOR EMPLOYMENT, INDUSTRIAL PRODUCTION, REGIONAL DATA,
    # TRADE, LEADING INDICATORS, ADDITIONAL INFLATION - January 2026 Expansion
    # ==========================================================================

    # === ADDITIONAL SECTOR EMPLOYMENT (Supplementary CES SERIES) ===
    # These provide more granular industry breakdowns beyond the main supersector series
    {"id": "CES6562100001", "name": "Healthcare Employment (Hospitals)",
     "description": "Employment in hospitals specifically. Inpatient care, emergency rooms, surgical centers, hospital nurses, orderlies, medical technicians, hospital administrators. Largest employment subsector in healthcare. Stable employment, growing with aging population."},
    {"id": "CES7072000001", "name": "Accommodation and Food Services Employment",
     "description": "Employment in hotels, restaurants, bars, catering, food trucks. Highly cyclical sector devastated during COVID. Major employer of young workers, part-time workers, and immigrants. Sensitive to discretionary spending."},
    {"id": "CES4348100001", "name": "Transportation and Warehousing Employment",
     "description": "Employment in transportation and warehousing. Truckers, airline workers, rail, shipping, couriers, Amazon/FedEx warehouse workers. Critical supply chain indicator tracking goods movement through economy."},
    {"id": "CES5500000001", "name": "Finance and Insurance Employment",
     "description": "Employment in finance and insurance subsector. Banks, credit unions, insurance companies, investment firms, asset managers. Reflects financial sector health. Sensitive to interest rates and market conditions."},
    {"id": "CES5552000001", "name": "Real Estate Employment",
     "description": "Employment in real estate. Realtors, property managers, appraisers, title companies, property developers. Directly tied to housing market activity, transaction volumes, and commercial real estate."},
    {"id": "CES1000000001", "name": "Mining and Logging Employment (CES)",
     "description": "Employment in mining and logging. Oil and gas extraction, coal mining, metal ores, timber harvesting. Very sensitive to commodity prices and energy sector boom/bust cycles. Alternative to USMINE."},
    {"id": "CES6100000001", "name": "Private Education Services Employment",
     "description": "Employment in private educational services. Private K-12 schools, colleges, tutoring centers, test prep, vocational training. Does not include public school teachers."},
    {"id": "CES7071000001", "name": "Arts and Entertainment Employment",
     "description": "Employment in arts, entertainment, and recreation. Movie theaters, sports teams, concert venues, museums, casinos, fitness centers. Highly sensitive to discretionary consumer spending."},
    {"id": "CES3100000001", "name": "Durable Goods Manufacturing Employment",
     "description": "Employment in durable goods manufacturing. Factories producing long-lasting products like cars, appliances, furniture, machinery. Cyclically sensitive, key indicator of manufacturing sector health."},
    {"id": "CES3200000001", "name": "Nondurable Goods Manufacturing Employment",
     "description": "Employment in nondurable goods manufacturing. Food processing, textiles, chemicals, plastics, paper. More stable than durables. Includes essential goods production."},

    # === INDUSTRIAL PRODUCTION INDEXES ===
    {"id": "IPMAN", "name": "Industrial Production: Manufacturing",
     "description": "Industrial production index for total manufacturing. Overall factory output across all manufacturing industries. Core measure of US industrial activity and manufacturing health."},
    {"id": "IPG331S", "name": "Industrial Production: Primary Metals",
     "description": "Industrial production index for primary metals. Steel mills, aluminum smelters, copper refineries. Key input for construction, auto manufacturing, infrastructure. Sensitive to tariffs and trade policy."},
    {"id": "IPG3361T3S", "name": "Industrial Production: Motor Vehicles",
     "description": "Industrial production index for motor vehicles and parts. Auto assembly plants and parts suppliers. Indicator of consumer durables demand and manufacturing supply chains."},
    {"id": "IPG325S", "name": "Industrial Production: Chemicals",
     "description": "Industrial production for chemical manufacturing. Pharmaceuticals, plastics, fertilizers, industrial chemicals. Broad indicator with diverse end markets from healthcare to agriculture."},
    {"id": "IPG334S", "name": "Industrial Production: Computer and Electronics",
     "description": "Industrial production for computers and electronic products. Semiconductors, computers, communications equipment. Technology hardware manufacturing, sensitive to chip supply."},
    {"id": "IPDMAN", "name": "Industrial Production: Durable Goods",
     "description": "Industrial production index for all durable goods manufacturing. Long-lasting products from appliances to aircraft. Economically sensitive, falls sharply in recessions."},
    {"id": "IPNMAN", "name": "Industrial Production: Nondurable Goods",
     "description": "Industrial production for nondurable goods. Food, beverages, apparel, paper, petroleum products. Less cyclical than durables, includes essentials."},
    {"id": "IPUTIL", "name": "Industrial Production: Utilities",
     "description": "Industrial production index for electric and gas utilities. Electricity generation, natural gas distribution. Weather-sensitive, provides baseline economic activity."},
    {"id": "IPB50001N", "name": "Industrial Production: Consumer Goods",
     "description": "Industrial production index for total consumer goods. All products purchased by households. Direct indicator of consumer demand and retail supply."},
    {"id": "IPB51000S", "name": "Industrial Production: Business Equipment",
     "description": "Industrial production for business equipment. Machinery, computers, office equipment, industrial equipment. Key indicator of business capital investment intentions."},
    {"id": "IPG311A2S", "name": "Industrial Production: Food Manufacturing",
     "description": "Industrial production for food manufacturing. Food processing, meat packing, beverages. Essential sector, less cyclical, affected by agricultural inputs and labor."},
    {"id": "IPG324S", "name": "Industrial Production: Petroleum and Coal",
     "description": "Industrial production for petroleum and coal products. Refineries, fuel production, asphalt. Sensitive to oil prices and energy demand."},

    # === REGIONAL DATA - STATE UNEMPLOYMENT ===
    {"id": "TXUR", "name": "Texas Unemployment Rate",
     "description": "Unemployment rate for Texas. Second largest state economy with energy, technology, and manufacturing sectors. Sunbelt growth story and energy sector exposure."},
    {"id": "CAUR", "name": "California Unemployment Rate",
     "description": "Unemployment rate for California. Largest state economy - tech, entertainment, agriculture, trade. West Coast bellwether, often higher unemployment than national average."},
    {"id": "NYUR", "name": "New York Unemployment Rate",
     "description": "Unemployment rate for New York. Major financial center with Wall Street, media, healthcare. Northeast corridor economic indicator."},
    {"id": "FLUR", "name": "Florida Unemployment Rate",
     "description": "Unemployment rate for Florida. Tourism, real estate, and retirement-driven economy. Major migration destination, sensitive to hospitality and housing sectors."},
    {"id": "PAUR", "name": "Pennsylvania Unemployment Rate",
     "description": "Unemployment rate for Pennsylvania. Healthcare, manufacturing, energy. Mix of Rust Belt legacy and energy renaissance."},
    {"id": "OHUR", "name": "Ohio Unemployment Rate",
     "description": "Unemployment rate for Ohio. Manufacturing belt state with automotive and industrial base. Politically important swing state economic indicator."},
    {"id": "ILUR", "name": "Illinois Unemployment Rate",
     "description": "Unemployment rate for Illinois. Chicago metro economy with finance, manufacturing, and transportation. Midwest regional hub."},
    {"id": "GAUR", "name": "Georgia Unemployment Rate",
     "description": "Unemployment rate for Georgia. Atlanta metro - major corporate headquarters, logistics hub. Southeast economic indicator."},
    {"id": "MIUR", "name": "Michigan Unemployment Rate",
     "description": "Unemployment rate for Michigan. Auto industry capital - Detroit Big Three and suppliers. Most sensitive state to auto sector conditions."},
    {"id": "NCUR", "name": "North Carolina Unemployment Rate",
     "description": "Unemployment rate for North Carolina. Charlotte banking, Research Triangle tech, furniture manufacturing. Fast-growing Sunbelt state."},
    {"id": "WAUR", "name": "Washington Unemployment Rate",
     "description": "Unemployment rate for Washington State. Seattle tech giants (Amazon, Microsoft), Boeing aerospace, trade with Asia. Pacific Northwest tech hub indicator."},
    {"id": "AZUR", "name": "Arizona Unemployment Rate",
     "description": "Unemployment rate for Arizona. Phoenix metro, semiconductor manufacturing, Sunbelt migration. Fast growth state with construction and tech."},

    # === REGIONAL HOUSING - CASE-SHILLER METRO INDEXES ===
    {"id": "LXXRSA", "name": "Case-Shiller: Los Angeles Home Prices",
     "description": "S&P Case-Shiller home price index for Los Angeles metro. West Coast housing bellwether. Entertainment industry and immigrant wealth influences."},
    {"id": "NYXRSA", "name": "Case-Shiller: New York Home Prices",
     "description": "S&P Case-Shiller home price index for New York metro. Northeast corridor housing. Financial sector wealth, urban density, international buyers."},
    {"id": "SFXRSA", "name": "Case-Shiller: San Francisco Home Prices",
     "description": "S&P Case-Shiller home price index for San Francisco metro. Silicon Valley tech wealth impact. Most volatile to tech industry fortunes."},
    {"id": "CHXRSA", "name": "Case-Shiller: Chicago Home Prices",
     "description": "S&P Case-Shiller home price index for Chicago metro. Midwest housing benchmark. More affordable than coasts, different dynamics."},
    {"id": "MIAXRSA", "name": "Case-Shiller: Miami Home Prices",
     "description": "S&P Case-Shiller home price index for Miami metro. Florida housing market. Strong international and Latin American buyer influence."},
    {"id": "DAXRSA", "name": "Case-Shiller: Dallas Home Prices",
     "description": "S&P Case-Shiller home price index for Dallas metro. Texas housing, rapid population growth. Corporate relocations and affordability migration."},
    {"id": "SEXRSA", "name": "Case-Shiller: Seattle Home Prices",
     "description": "S&P Case-Shiller home price index for Seattle metro. Pacific Northwest, tech-driven demand. Amazon HQ and Microsoft campus effects."},
    {"id": "PHXRSA", "name": "Case-Shiller: Phoenix Home Prices",
     "description": "S&P Case-Shiller home price index for Phoenix metro. Sunbelt migration destination with boom-bust history. Remote work migration acceleration."},
    {"id": "DEXRSA", "name": "Case-Shiller: Denver Home Prices",
     "description": "S&P Case-Shiller home price index for Denver metro. Mountain West housing. Outdoor lifestyle, remote work, cannabis industry effects."},
    {"id": "ATXRSA", "name": "Case-Shiller: Atlanta Home Prices",
     "description": "S&P Case-Shiller home price index for Atlanta metro. Southeast regional hub. Corporate headquarters relocations, logistics growth."},

    # === TRADE - IMPORTS/EXPORTS ===
    {"id": "BOPGTB", "name": "Goods Trade Balance",
     "description": "US trade balance in goods only (excluding services). Goods exports minus goods imports. Reflects manufacturing competitiveness and consumer goods demand. US runs persistent goods deficit."},
    {"id": "BOPSTB", "name": "Services Trade Balance",
     "description": "US trade balance in services. Services exports minus imports. US typically runs surplus in financial services, tourism, intellectual property, software."},
    {"id": "EXPGSC1", "name": "Real Exports of Goods and Services",
     "description": "Real inflation-adjusted exports of goods and services. Volume of US exports reflecting global demand for American products. GDP component tracking US competitiveness."},
    {"id": "IMPGSC1", "name": "Real Imports of Goods and Services",
     "description": "Real inflation-adjusted imports of goods and services. Volume of imports reflecting domestic demand for foreign goods. Rises when US economy is strong."},
    {"id": "IMP0004", "name": "Imports: Capital Goods",
     "description": "US imports of capital goods - machinery, computers, equipment. Business investment indicator. Shows demand for productive equipment and supply chain dependency."},
    {"id": "IMP0005", "name": "Imports: Automotive Products",
     "description": "US imports of motor vehicles and parts. Foreign car and parts imports. Trade policy sensitive - tariff discussions affect this series."},
    {"id": "IMP0006", "name": "Imports: Consumer Goods",
     "description": "US imports of consumer goods. Electronics, apparel, toys, furniture from abroad. Consumer demand indicator, retail inventory supply."},
    {"id": "EXP0004", "name": "Exports: Capital Goods",
     "description": "US exports of capital goods. American machinery, aircraft, industrial equipment sold abroad. Manufacturing competitiveness and global capex demand."},
    {"id": "EXP0015", "name": "Exports: Agricultural Products",
     "description": "US exports of agricultural products. Grains, soybeans, meat, cotton exports. Farm economy indicator. Sensitive to China trade and dollar strength."},
    {"id": "XTEXVA01CNM667S", "name": "Exports to China",
     "description": "US goods exports to China. Bilateral trade indicator. Highly sensitive to tariffs, trade negotiations, geopolitical tensions."},
    {"id": "XTIMVA01CNM667S", "name": "Imports from China",
     "description": "US goods imports from China. China import dependency metric. Tariff policy implications, supply chain decoupling discussions."},

    # === LEADING/LAGGING INDICATORS ===
    {"id": "CFNAI", "name": "Chicago Fed National Activity Index",
     "description": "Chicago Fed National Activity Index (CFNAI). Weighted average of 85 monthly indicators. Zero means trend growth, positive is above trend, negative is below trend. Real-time economy barometer."},
    {"id": "USPHCI", "name": "Philadelphia Fed Coincident Index",
     "description": "Philadelphia Fed coincident economic activity index. Four-variable indicator measuring current economic state. Shows where economy is right now."},
    {"id": "STLFSI4", "name": "St. Louis Fed Financial Stress Index",
     "description": "St. Louis Fed financial stress index. Measures financial market stress using 18 weekly series. Zero is normal, positive is stress, negative is accommodative."},
    {"id": "NFCI", "name": "Chicago Fed Financial Conditions Index",
     "description": "Chicago Fed national financial conditions index. Measures risk, credit, and leverage conditions. Negative means loose financial conditions, positive means tight."},
    {"id": "ANFCI", "name": "Adjusted National Financial Conditions Index",
     "description": "Chicago Fed adjusted NFCI controlling for economic conditions. Isolates pure financial conditions from growth effects. Shows if finance helping or hindering economy."},
    {"id": "KCFSI", "name": "Kansas City Fed Financial Stress Index",
     "description": "Kansas City Fed financial stress index. Alternative stress measure using yield spreads, volatility, asset prices. Zero is normal, positive shows elevated stress."},
    {"id": "TEDRATE", "name": "TED Spread",
     "description": "TED spread - difference between 3-month LIBOR and 3-month Treasury bill rate. Measures credit risk and bank funding stress. Spikes during financial crises."},

    # === ADDITIONAL INFLATION MEASURES ===
    {"id": "CUUR0000SAM", "name": "CPI: Medical Care",
     "description": "Consumer price index for medical care. Healthcare costs including hospital services, physician services, prescription drugs, insurance premiums. Major household expense."},
    {"id": "CUUR0000SAE1", "name": "CPI: Education and Communication",
     "description": "Consumer price index for education and communication. College tuition, internet services, phone services, educational materials. Student and technology costs."},
    {"id": "CUUR0000SETA01", "name": "CPI: New Vehicles",
     "description": "Consumer price index for new vehicles. New car and truck prices. Auto industry pricing power. Supply chain and chip shortage effects."},
    {"id": "CUUR0000SETA02", "name": "CPI: Used Cars and Trucks",
     "description": "Consumer price index for used vehicles. Secondary market car prices. Extremely volatile - spiked 40% during chip shortage. Supply-driven inflation component."},
    {"id": "CUSR0000SEHA", "name": "CPI: Rent of Primary Residence",
     "description": "Consumer price index for actual rent paid by tenants. RENT INFLATION, rental prices, rent CPI, apartment rent costs, tenant housing costs, is rent inflation coming down, is rent going up, rental market inflation, what tenants pay, lease costs, monthly rent, rental inflation rate. Lags market rents (Zillow) by 6-12 months due to slow lease turnover - when Zillow rents fall, CPI rent takes a year to follow. Key for answering 'is rent inflation coming down' questions."},
    {"id": "CUSR0000SEHC", "name": "CPI: Owners Equivalent Rent (OER)",
     "description": "Consumer price index for owners equivalent rent. Imputed housing cost for homeowners based on what their home would rent for. OER, homeowner housing costs, imputed rent, housing inflation for owners. Largest single CPI component at ~25% weight. Drives shelter inflation which drives core CPI."},
    {"id": "CUSR0000SEHC01", "name": "CPI: Owners Equivalent Rent (OER) - Detailed",
     "description": "Detailed owners equivalent rent index. Imputed housing cost for homeowners based on rental market. Housing inflation, shelter costs, homeowner equivalent rent."},
    {"id": "PPIFIS", "name": "PPI: Final Demand Services",
     "description": "Producer price index for final demand services. Business-to-business service costs. Upstream service inflation before reaching consumers."},
    {"id": "PPIFGS", "name": "PPI: Final Demand Goods",
     "description": "Producer price index for final demand goods. Wholesale goods prices. Manufacturing costs and pricing before retail markup."},
    {"id": "PPIACO", "name": "PPI: All Commodities",
     "description": "Producer price index for all commodities. Raw material and commodity prices at producer level. Input cost inflation measure, leads consumer prices."},
    {"id": "CPIUFDSL", "name": "CPI: Food at Home",
     "description": "Consumer price index for food at home (groceries). Supermarket prices. Affects all households, politically sensitive inflation component."},
    {"id": "CPIENGSL", "name": "CPI: Energy",
     "description": "Consumer price index for energy. Gasoline, electricity, natural gas, fuel oil. Most volatile CPI component, driven by oil prices."},

    # === LABOR MARKET DETAILS ===
    {"id": "UNEMPLOY", "name": "Number of Unemployed Persons",
     "description": "Total number of unemployed persons. Absolute count of job seekers. Provides context beyond unemployment rate - shows scale of joblessness."},
    {"id": "CLF16OV", "name": "Civilian Labor Force Level",
     "description": "Total civilian labor force - employed plus unemployed. Labor supply measure. Growth driven by demographics and participation rate changes."},
    {"id": "UEMPMEAN", "name": "Average Duration of Unemployment",
     "description": "Average weeks unemployed for all unemployed persons. How long typical job search takes. Long durations indicate structural labor market problems."},
    {"id": "LNS13025703", "name": "Unemployed Job Leavers",
     "description": "Unemployed persons who voluntarily quit their previous job. Workers confident enough to quit before having new job. Labor market confidence indicator."},
    {"id": "LNS13023653", "name": "Unemployed Job Losers",
     "description": "Unemployed persons who were laid off or fired. Involuntary job loss. Rising job losers signals deteriorating labor market conditions."},
    {"id": "JTSLDR", "name": "JOLTS Layoffs and Discharges Rate",
     "description": "JOLTS layoffs and discharges as percent of employment. Involuntary separations rate. Low rate means strong job security."},
    {"id": "JTSHIR", "name": "JOLTS Hires Rate",
     "description": "JOLTS hires rate as percent of employment. Pace of new hiring. Shows labor market dynamism and employer willingness to hire."},
    {"id": "AWHNONAG", "name": "Average Weekly Hours: Private Sector",
     "description": "Average weekly hours worked in private sector. Leading indicator - employers adjust hours before headcount. Falling hours may precede layoffs."},

    # === ADDITIONAL HOUSING METRICS ===
    {"id": "HOUSTW", "name": "Housing Starts: West Region",
     "description": "New residential construction starts in Western US. West coast and mountain state building activity. High cost markets with supply constraints."},
    {"id": "HOUSTS", "name": "Housing Starts: South Region",
     "description": "New residential construction starts in Southern US. Sunbelt building boom. Fastest growing region driven by migration and affordability."},
    {"id": "HOUSTNE", "name": "Housing Starts: Northeast Region",
     "description": "New residential construction starts in Northeast US. High cost, supply constrained coastal markets. Limited buildable land."},
    {"id": "HOUSTMW", "name": "Housing Starts: Midwest Region",
     "description": "New residential construction starts in Midwest US. Heartland building. More affordable markets with different demand dynamics."},
    {"id": "MSACSR", "name": "Months Supply of New Houses",
     "description": "Months supply of new houses for sale. Inventory divided by sales pace. Below 4 months is seller's market, above 6 months is buyer's market."},
    {"id": "ACTLISCOUUS", "name": "Active Housing Listings Count",
     "description": "Active housing listings in the US. Total homes for sale. Inventory indicator - low listings drive price increases."},
    {"id": "USSTHPI", "name": "FHFA House Price Index",
     "description": "FHFA all-transactions house price index. Broadest US house price measure including purchases and refinance appraisals. National benchmark."},
    {"id": "FIXHAI", "name": "Housing Affordability Index",
     "description": "Housing affordability index. Whether median family income can afford median home at current rates. Index below 100 means housing unaffordable."},

    # === GDP COMPONENTS AND DETAILS ===
    {"id": "DPCERL1Q225SBEA", "name": "Real Personal Consumption Growth",
     "description": "Real personal consumption expenditures quarterly growth annualized. Consumer spending volume change. PCE is 70% of GDP, drives business cycle."},
    {"id": "GPDIC1", "name": "Real Private Investment",
     "description": "Real gross private domestic investment. Business equipment, structures, residential, inventory investment. Most volatile GDP component, drives recessions."},
    {"id": "A191RC1Q027SBEA", "name": "GDP Implicit Price Deflator",
     "description": "GDP price deflator. Broadest price measure covering all domestic production. Alternative inflation measure to CPI and PCE."},
    {"id": "DGORDER", "name": "Durable Goods New Orders",
     "description": "Manufacturers new orders for durable goods. Big-ticket factory orders. Volatile but important forward indicator for manufacturing."},
    {"id": "NEWORDER", "name": "All Manufacturing New Orders",
     "description": "Total new orders all manufacturing industries. Factory order flow. Forward indicator of production and business activity."},
    {"id": "AMTMNO", "name": "Manufacturers Shipments",
     "description": "Value of manufacturers shipments. Goods shipped from factories. Current production activity measure."},
    {"id": "AMTMUO", "name": "Manufacturers Unfilled Orders",
     "description": "Manufacturers unfilled orders backlog. Orders received but not shipped. Future production pipeline, capacity indicator."},
    {"id": "AMDMUO", "name": "Durable Goods Unfilled Orders",
     "description": "Unfilled orders backlog for durable goods. Big-ticket items awaiting production. Capacity utilization and demand strength."},

    # ==========================================================================
    # COMPREHENSIVE ADDITIONS - January 2026
    # Critical series for common query patterns that were previously missing
    # ==========================================================================

    # === INFLATION COMPONENTS - DETAILED BREAKDOWN ===
    {"id": "CUSR0000SA0L1E", "name": "CPI: All Items Less Food and Energy",
     "description": "Core CPI inflation excluding volatile food and energy. Core inflation rate, underlying inflation, inflation ex food and energy. The standard 'core' measure economists watch for underlying price pressures."},
    {"id": "CUSR0000SA0L2", "name": "CPI: All Items Less Shelter",
     "description": "CPI excluding shelter/housing. Inflation without rent, non-housing inflation. Shows what inflation looks like if you strip out the sticky housing component."},
    {"id": "CUSR0000SA0L5", "name": "CPI: All Items Less Medical Care",
     "description": "CPI excluding medical care costs. Inflation without healthcare, non-medical inflation."},
    {"id": "CUSR0000SAS", "name": "CPI: Services",
     "description": "Consumer price index for all services. Service sector inflation, services prices, non-goods inflation. Services are stickier than goods inflation."},
    {"id": "CUSR0000SACL1E", "name": "CPI: Commodities Less Food and Energy",
     "description": "Core goods inflation excluding food and energy. Goods prices, merchandise inflation, physical product prices."},
    {"id": "CUSR0000SAH2", "name": "CPI: Fuels and Utilities",
     "description": "Consumer price index for fuels and utilities. Energy bills, utility costs, heating fuel, electricity bills, natural gas bills, home energy costs."},
    {"id": "CUSR0000SAH3", "name": "CPI: Household Furnishings and Operations",
     "description": "CPI for furniture, appliances, household supplies. Home goods prices, furniture inflation, appliance costs."},
    {"id": "CUSR0000SAA", "name": "CPI: Apparel",
     "description": "Consumer price index for clothing and apparel. Clothing prices, fashion costs, apparel inflation, what clothes cost."},
    {"id": "CUSR0000SAT", "name": "CPI: Transportation",
     "description": "Consumer price index for transportation. Vehicle prices, car costs, transportation inflation, commuting costs, airfares, public transit fares."},
    {"id": "CUSR0000SETB", "name": "CPI: Motor Fuel",
     "description": "Consumer price index for all motor fuel. Gas prices, fuel costs, gasoline inflation, diesel prices, what you pay at the pump."},
    {"id": "CUSR0000SEHF", "name": "CPI: Energy Services",
     "description": "Consumer price index for energy services. Electricity prices, utility rates, piped gas, home energy inflation."},
    {"id": "CUSR0000SEHF01", "name": "CPI: Electricity",
     "description": "Consumer price index specifically for electricity. Electric bills, power costs, electricity rates, electricity inflation."},
    {"id": "CUSR0000SEHF02", "name": "CPI: Utility (Piped) Gas Service",
     "description": "Consumer price index for natural gas utility service. Gas bills, heating costs, natural gas prices for homes."},
    {"id": "CUSR0000SS4501A", "name": "CPI: Hospital Services",
     "description": "Consumer price index for hospital and related services. Hospital costs, inpatient care costs, medical facility prices."},
    {"id": "CPIMEDSL", "name": "CPI: Medical Care Services",
     "description": "Consumer price index for medical care services. Healthcare inflation, doctor visits, medical costs, health services prices."},

    # === SUPERCORE AND ALTERNATIVE INFLATION MEASURES ===
    {"id": "CORESTICKM157SFRBATL", "name": "Sticky Price CPI",
     "description": "Atlanta Fed sticky price CPI. Prices that change infrequently, sticky inflation, underlying inflation trends. Better signal of persistent inflation."},
    {"id": "CORESTICKM158SFRBATL", "name": "Sticky Price CPI Less Shelter",
     "description": "Atlanta Fed sticky price CPI excluding shelter. Sticky core inflation without housing, supercore sticky inflation."},
    {"id": "FLEXCPIM157SFRBATL", "name": "Flexible Price CPI",
     "description": "Atlanta Fed flexible price CPI. Prices that change frequently, volatile inflation components."},
    {"id": "TRMMEANCPIM158SFRBCLE", "name": "Trimmed Mean PCE Inflation",
     "description": "Cleveland Fed trimmed mean PCE inflation. Removes outliers from PCE for cleaner inflation signal. Alternative core inflation measure."},
    {"id": "MEDCPIM158SFRBCLE", "name": "Median CPI",
     "description": "Cleveland Fed median CPI. The median price change across all items, removes influence of outliers. Persistent inflation signal."},
    {"id": "PCETRIM1M158SFRBDAL", "name": "Dallas Fed Trimmed Mean PCE",
     "description": "Dallas Fed trimmed mean PCE inflation rate. Removes extremes for cleaner inflation reading. Fed-preferred alternative inflation gauge."},
    {"id": "BPCCRO1Q156NBEA", "name": "PCE Chain-Type Price Index Growth",
     "description": "PCE price index quarterly growth rate. Fed's preferred inflation measure growth rate, PCE inflation annualized."},

    # === WAGE INFLATION AND LABOR COSTS ===
    {"id": "ECIWAG", "name": "Employment Cost Index: Wages",
     "description": "Employment cost index for wages and salaries. Wage inflation, wage growth, pay increases, salary inflation. Most comprehensive wage measure."},
    {"id": "ECIALLCIV", "name": "Employment Cost Index: Total Compensation",
     "description": "Employment cost index for total compensation including benefits. Total labor costs, compensation growth, wages plus benefits."},
    {"id": "CES0500000003", "name": "Average Hourly Earnings: All Private",
     "description": "Average hourly earnings for all private employees. Wage growth, pay levels, hourly pay, what workers earn per hour."},
    {"id": "CES0500000011", "name": "Average Weekly Earnings: All Private",
     "description": "Average weekly earnings for all private employees. Weekly pay, take-home pay, total weekly earnings."},
    {"id": "COMPRNFB", "name": "Real Compensation Per Hour: Nonfarm Business",
     "description": "Real hourly compensation in nonfarm business sector. Inflation-adjusted pay, real wage growth, purchasing power of wages."},
    {"id": "OPHNFB", "name": "Nonfarm Business Output Per Hour",
     "description": "Labor productivity - output per hour worked in nonfarm business. Productivity growth, worker efficiency, how much workers produce."},
    {"id": "ULCNFB", "name": "Unit Labor Costs: Nonfarm Business",
     "description": "Unit labor costs in nonfarm business. Labor cost per unit of output, wage-productivity balance, cost of labor per unit produced."},

    # === HOUSING AFFORDABILITY AND MARKET DYNAMICS ===
    {"id": "HOUST1F", "name": "Housing Starts: Single Family",
     "description": "New single-family housing starts. Single family home construction, house building, new home construction starts."},
    {"id": "HOUST5F", "name": "Housing Starts: 5+ Units",
     "description": "Housing starts for buildings with 5+ units. Apartment construction, multifamily building, apartment development."},
    {"id": "PERMIT1", "name": "Building Permits: Single Family",
     "description": "Building permits for single-family homes. Future single-family construction, home building permits."},
    {"id": "COMPUTSA", "name": "Housing Units Under Construction",
     "description": "Total housing units currently under construction. Construction pipeline, housing supply in progress."},
    {"id": "COMPU1USA", "name": "Single Family Units Under Construction",
     "description": "Single-family homes currently under construction. House building pipeline, homes being built."},
    {"id": "ETOTALUSQ176N", "name": "Housing Inventory Estimate",
     "description": "Total housing units in the United States. Housing stock, total homes, housing supply."},
    {"id": "ASPUS", "name": "Average Sales Price of Houses Sold",
     "description": "Average home sale price. House prices, home costs, what homes sell for on average."},
    {"id": "USHOWN", "name": "Homeownership Rate",
     "description": "US homeownership rate. Percent of households owning homes, homeowner share, ownership vs renting."},
    {"id": "HCAI", "name": "Housing Credit Availability Index",
     "description": "Urban Institute housing credit availability index. Mortgage lending standards, how easy to get a mortgage, credit access for homebuyers."},

    # === CONSUMER FINANCIAL HEALTH ===
    {"id": "TDSP", "name": "Household Debt Service Ratio",
     "description": "Household debt service payments as percent of disposable income. Debt burden, how much income goes to debt payments, consumer financial stress."},
    {"id": "FODSP", "name": "Financial Obligations Ratio",
     "description": "Financial obligations ratio for households. Debt plus rent, auto leases, insurance as share of income. Broader debt burden measure."},
    {"id": "CDSP", "name": "Consumer Debt Service Ratio",
     "description": "Consumer debt service payments as percent of income. Non-mortgage debt burden, credit card and auto loan payments."},
    {"id": "MDSP", "name": "Mortgage Debt Service Ratio",
     "description": "Mortgage debt service as percent of income. Housing debt burden, mortgage payment share of income."},
    {"id": "BOGZ1FL153020005Q", "name": "Household Net Worth",
     "description": "Total household net worth. Wealth, assets minus liabilities, American household wealth, how rich are households."},
    {"id": "HNOREMQ027S", "name": "Household Real Estate Holdings",
     "description": "Household real estate value. Home equity, homeowner wealth, housing wealth of Americans."},
    {"id": "HNOFDTIQ027S", "name": "Household Financial Assets",
     "description": "Household financial assets. Stocks, bonds, savings, 401k, investment holdings of households."},

    # === BUSINESS AND CORPORATE HEALTH ===
    {"id": "CP", "name": "Corporate Profits",
     "description": "Corporate profits after tax. Business earnings, company profits, corporate America earnings, how much companies make."},
    {"id": "CPATAX", "name": "Corporate Profits After Tax",
     "description": "Corporate profits after tax with inventory and capital consumption adjustments. Adjusted business profits."},
    {"id": "A053RC1Q027SBEA", "name": "Corporate Profits Before Tax",
     "description": "Corporate profits before tax. Pre-tax business earnings, gross corporate profits."},
    {"id": "BOGZ1FA106000105Q", "name": "Nonfinancial Corporate Debt",
     "description": "Nonfinancial corporate business debt. Corporate borrowing, business debt levels, company leverage."},
    {"id": "NCBCMDPMVCE", "name": "Market Value of Corporate Equities",
     "description": "Market value of nonfinancial corporate equities. Stock market value, corporate America market cap."},
    {"id": "BUSINSMNSA", "name": "Business Inventories",
     "description": "Total business inventories. Inventory levels, stock on hand, business stockpiles."},
    {"id": "RETAILIMSA", "name": "Retail Inventories",
     "description": "Retail inventory levels. Store stock, retail stockpiles, what retailers have on shelves."},
    {"id": "ISRATIO", "name": "Inventory to Sales Ratio",
     "description": "Business inventories to sales ratio. Inventory efficiency, stock turnover, how long inventory lasts."},

    # === ADDITIONAL LABOR MARKET DETAILS ===
    {"id": "UEMPLT5", "name": "Unemployed Less Than 5 Weeks",
     "description": "Number unemployed less than 5 weeks. Short-term unemployment, newly unemployed, recent job losers."},
    {"id": "UEMP5TO14", "name": "Unemployed 5-14 Weeks",
     "description": "Number unemployed 5-14 weeks. Medium-term unemployment, job seekers for 1-3 months."},
    {"id": "UEMP15T26", "name": "Unemployed 15-26 Weeks",
     "description": "Number unemployed 15-26 weeks. Longer unemployment spell, 4-6 months without work."},
    {"id": "UEMP27OV", "name": "Unemployed 27 Weeks and Over",
     "description": "Long-term unemployed 27+ weeks. Long-term unemployment, chronically jobless, 6+ months without work."},
    {"id": "U1RATE", "name": "Unemployment Rate: U-1",
     "description": "U-1 unemployment rate - persons unemployed 15 weeks or longer. Long-term unemployment rate."},
    {"id": "U2RATE", "name": "Unemployment Rate: U-2",
     "description": "U-2 unemployment rate - job losers and completed temporary jobs. Involuntary unemployment."},
    {"id": "U4RATE", "name": "Unemployment Rate: U-4",
     "description": "U-4 unemployment rate including discouraged workers. Broader unemployment including those who stopped looking."},
    {"id": "U5RATE", "name": "Unemployment Rate: U-5",
     "description": "U-5 unemployment rate including marginally attached workers. Even broader unemployment measure."},
    {"id": "LNS12032194", "name": "Part-Time for Economic Reasons",
     "description": "Employed part-time for economic reasons. Underemployed workers, involuntary part-time, want full-time but can only get part-time."},
    {"id": "LNS13008636", "name": "Not in Labor Force: Want a Job",
     "description": "Not in labor force but want a job. Hidden unemployment, potential workers on sidelines."},
    {"id": "LNS15026636", "name": "Discouraged Workers",
     "description": "Discouraged workers not looking because no jobs available. Given up looking, believe no work available."},

    # === ZILLOW HOUSING DATA (NON-FRED) ===
    {"id": "zillow_zori_national", "name": "Zillow Observed Rent Index (ZORI)",
     "description": "Market rents, asking rents, real-time rent prices, rental market, what landlords charge. More timely than CPI rent which lags 12+ months."},
    {"id": "zillow_rent_yoy", "name": "Zillow Rent Year-over-Year Growth",
     "description": "Rent inflation, rent growth rate, rental price changes. Real-time rent trends before they appear in CPI."},
    {"id": "zillow_zhvi_national", "name": "Zillow Home Value Index (ZHVI)",
     "description": "Home values, house prices, real estate values, typical home price. More timely than Case-Shiller."},
    {"id": "zillow_home_value_yoy", "name": "Zillow Home Value Year-over-Year Growth",
     "description": "Home price appreciation, house price growth, real estate value changes."},

    # === EIA ENERGY DATA (NON-FRED) ===
    {"id": "eia_wti_crude", "name": "WTI Crude Oil Price (EIA)",
     "description": "Oil price, crude oil, WTI, petroleum price. US benchmark oil price from Energy Information Administration."},
    {"id": "eia_brent_crude", "name": "Brent Crude Oil Price (EIA)",
     "description": "Brent oil, global oil benchmark, international crude price."},
    {"id": "eia_gasoline_retail", "name": "Retail Gasoline Price (EIA)",
     "description": "Gas prices, gasoline cost, pump price, fuel cost. What consumers pay at the gas station."},
    {"id": "eia_diesel_retail", "name": "Retail Diesel Price (EIA)",
     "description": "Diesel prices, trucking fuel, commercial fuel cost."},
    {"id": "eia_natural_gas_henry_hub", "name": "Natural Gas Price - Henry Hub (EIA)",
     "description": "Natural gas price, Henry Hub, heating fuel, utility gas price."},
    {"id": "eia_crude_stocks", "name": "US Crude Oil Inventories (EIA)",
     "description": "Oil inventories, crude stocks, petroleum reserves. Higher stocks typically mean lower prices."},
    {"id": "eia_crude_production", "name": "US Crude Oil Production (EIA)",
     "description": "Oil production, US drilling output, domestic crude supply."},

    # === ALPHA VANTAGE MARKET DATA (NON-FRED) ===
    {"id": "av_spy", "name": "S&P 500 ETF (SPY) - Daily",
     "description": "S&P 500 daily, stock market daily, equity market. More frequent than FRED's SP500."},
    {"id": "av_treasury_10y", "name": "10-Year Treasury Yield (Daily)",
     "description": "10-year yield daily, bond yield, treasury rate. Real-time bond market data."},
    {"id": "av_treasury_2y", "name": "2-Year Treasury Yield (Daily)",
     "description": "2-year yield daily, short-term treasury, Fed rate expectations."},
]

# =============================================================================
# EMBEDDING FUNCTIONS
# =============================================================================

_embeddings_cache = {}
_catalog_embeddings = None

def get_embedding(text: str) -> np.ndarray:
    """Get embedding for a text string. Tries Gemini first, then OpenAI."""
    if text in _embeddings_cache:
        return _embeddings_cache[text]

    # Try Gemini embeddings first
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text
            )
            embedding = np.array(result['embedding'])
            _embeddings_cache[text] = embedding
            return embedding
        except Exception as e:
            print(f"Gemini embedding error: {e}")

    # Fall back to OpenAI embeddings
    if OPENAI_API_KEY:
        url = 'https://api.openai.com/v1/embeddings'
        payload = {
            'model': 'text-embedding-3-small',
            'input': text
        }
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {OPENAI_API_KEY}'
        }

        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'),
                         headers=headers, method='POST')
            with urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                embedding = np.array(result['data'][0]['embedding'])
                _embeddings_cache[text] = embedding
                return embedding
        except Exception as e:
            print(f"OpenAI embedding error: {e}")

    return None


def get_batch_embeddings(texts: List[str]) -> List[np.ndarray]:
    """Get embeddings for multiple texts. Tries Gemini first, then OpenAI."""

    # Try Gemini embeddings first (processes one at a time but fast)
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            embeddings = []
            for text in texts:
                result = genai.embed_content(
                    model="models/text-embedding-004",
                    content=text
                )
                embeddings.append(np.array(result['embedding']))
            return embeddings
        except Exception as e:
            print(f"Gemini batch embedding error: {e}")

    # Fall back to OpenAI batch embeddings
    if OPENAI_API_KEY:
        url = 'https://api.openai.com/v1/embeddings'
        payload = {
            'model': 'text-embedding-3-small',
            'input': texts
        }
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {OPENAI_API_KEY}'
        }

        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'),
                         headers=headers, method='POST')
            with urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                embeddings = [np.array(d['embedding']) for d in result['data']]
                return embeddings
        except Exception as e:
            print(f"OpenAI batch embedding error: {e}")

    return None


def build_catalog_embeddings():
    """Build embeddings for all series in the catalog."""
    global _catalog_embeddings

    if _catalog_embeddings is not None:
        return _catalog_embeddings

    # Check if cached embeddings exist
    cache_path = Path(__file__).parent / 'series_embeddings.json'
    if cache_path.exists():
        with open(cache_path) as f:
            cached = json.load(f)
            _catalog_embeddings = {
                item['id']: np.array(item['embedding'])
                for item in cached
            }
            return _catalog_embeddings

    print("Building embeddings for FRED series catalog...")

    # Create search text for each series
    texts = []
    for series in FRED_SERIES_CATALOG:
        search_text = f"{series['name']}. {series['description']}"
        texts.append(search_text)

    # Get embeddings in batch
    embeddings = get_batch_embeddings(texts)

    if embeddings:
        _catalog_embeddings = {}
        cache_data = []
        for series, embedding in zip(FRED_SERIES_CATALOG, embeddings):
            _catalog_embeddings[series['id']] = embedding
            cache_data.append({
                'id': series['id'],
                'embedding': embedding.tolist()
            })

        # Cache to file
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f)

        print(f"Built embeddings for {len(_catalog_embeddings)} series")

    return _catalog_embeddings


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


# =============================================================================
# RAG RETRIEVAL
# =============================================================================

def keyword_score(query: str, series: Dict) -> float:
    """Compute keyword overlap score between query and series description."""
    query_words = set(query.lower().split())
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                  'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                  'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                  'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                  'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'like',
                  'through', 'after', 'over', 'between', 'out', 'against', 'during',
                  'without', 'before', 'under', 'around', 'among', 'what', 'how',
                  'why', 'when', 'where', 'which', 'who', 'whom', 'this', 'that',
                  'these', 'those', 'am', 'it', 'its', 'and', 'or', 'but', 'if',
                  'because', 'until', 'while', 'about', 'up', 'down', 'coming'}
    query_words = query_words - stop_words

    desc_text = f"{series['name']} {series['description']}".lower()
    desc_words = set(desc_text.split())

    if not query_words:
        return 0.0

    # Count matching words
    matches = query_words & desc_words
    # Bonus for phrase matches
    query_lower = query.lower()
    phrase_bonus = 0.0
    if series['id'].lower() in query_lower:
        phrase_bonus = 0.5
    if series['name'].lower() in query_lower:
        phrase_bonus = 0.3

    return (len(matches) / len(query_words)) + phrase_bonus


def retrieve_relevant_series(query: str, top_k: int = 15) -> List[Dict]:
    """
    Retrieve the most relevant FRED series for a query using semantic search.
    Falls back to keyword matching if embeddings fail.

    Args:
        query: User's question
        top_k: Number of candidates to return

    Returns:
        List of series dicts with similarity scores
    """
    # Ensure catalog embeddings are built
    catalog_embeddings = build_catalog_embeddings()

    # Get query embedding
    query_embedding = get_embedding(query) if catalog_embeddings else None

    if query_embedding is not None and catalog_embeddings:
        # Use semantic search with embeddings
        similarities = []
        for series in FRED_SERIES_CATALOG:
            series_embedding = catalog_embeddings.get(series['id'])
            if series_embedding is not None:
                sim = cosine_similarity(query_embedding, series_embedding)
                similarities.append({
                    **series,
                    'similarity': sim
                })

        # Sort by similarity and return top-k
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        return similarities[:top_k]

    else:
        # Fallback to keyword matching
        print("Using keyword-based retrieval (embeddings unavailable)")
        scored = []
        for series in FRED_SERIES_CATALOG:
            score = keyword_score(query, series)
            if score > 0:
                scored.append({
                    **series,
                    'similarity': score
                })

        scored.sort(key=lambda x: x['similarity'], reverse=True)
        return scored[:top_k]


# =============================================================================
# LLM SELECTION FROM CANDIDATES
# =============================================================================

def select_best_series(query: str, candidates: List[Dict], num_series: int = 4) -> Dict:
    """
    Have an LLM select the best series from retrieved candidates.

    Args:
        query: User's original question
        candidates: List of candidate series from retrieval
        num_series: Target number of series to select

    Returns:
        Dict with selected series and explanation
    """
    # Format candidates for the prompt
    candidate_text = "\n".join([
        f"- {c['id']}: {c['name']} - {c['description']}"
        for c in candidates
    ])

    prompt = f"""You are an expert economist. A user asked: "{query}"

Here are relevant FRED series candidates (retrieved by semantic search):

{candidate_text}

Select the {num_series} BEST series that directly answer the user's question.

CRITICAL RULES:
1. For demographic questions (immigrants, women, Black workers, etc.), ONLY use demographic-specific series. DO NOT use aggregate series like UNRATE or PAYEMS.
2. For "how is X doing?" questions, cover multiple dimensions: employment + wages + relevant prices if applicable.
3. Each series should add unique insight - no redundant measures.

COMBINE_CHART RULES (when to plot series together):
- Set combine_chart=true when: all series share compatible units (all rates, all percentages, all indexes)
- Set combine_chart=true for comparison queries: "X vs Y", "compare X and Y", "X and Y"
- Examples where combine_chart=TRUE: treasury yields (all rates), inflation measures (all %), unemployment rates (all %)
- Examples where combine_chart=FALSE: unemployment rate (%) + total payrolls (thousands) - different units

Return JSON only:
{{
    "series": ["ID1", "ID2", "ID3", "ID4"],
    "explanation": "Brief explanation of why these series answer the question",
    "show_yoy": false,
    "combine_chart": true or false based on unit compatibility
}}"""

    # Use Gemini for selection (fast, good at following instructions)
    try:
        import google.generativeai as genai
        GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', os.environ.get('GOOGLE_API_KEY', ''))
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = model.generate_content(prompt)
            content = response.text

            # Extract JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            return json.loads(content.strip())
    except Exception as e:
        print(f"Gemini selection error: {e}")

    # Fallback to Claude if Gemini fails
    try:
        import anthropic
        ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
        if ANTHROPIC_API_KEY:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.content[0].text

            # Extract JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            return json.loads(content.strip())
    except Exception as e:
        print(f"Claude selection error: {e}")

    # Final fallback: return top candidates by similarity
    return {
        'series': [c['id'] for c in candidates[:num_series]],
        'explanation': f"Top matches for: {query}",
        'show_yoy': False,
        'combine_chart': False
    }


# =============================================================================
# MAIN RAG FUNCTION
# =============================================================================

def rag_query_plan(query: str, verbose: bool = False) -> Dict:
    """
    Generate a query plan using RAG: retrieve relevant series, then select best ones.

    Args:
        query: User's question
        verbose: Whether to print progress

    Returns:
        Query plan dict with series, explanation, etc.
    """
    if verbose:
        print(f"RAG query plan for: {query}")

    # Step 1: Retrieve candidates via semantic search
    if verbose:
        print("  Retrieving candidates...")
    candidates = retrieve_relevant_series(query, top_k=15)

    if verbose:
        print(f"  Found {len(candidates)} candidates:")
        for c in candidates[:5]:
            print(f"    {c['id']}: {c['name']} (sim: {c['similarity']:.3f})")

    if not candidates:
        return {
            'series': [],
            'search_terms': [query],
            'explanation': 'No matching series found',
            'show_yoy': False,
            'combine_chart': False
        }

    # Step 2: Have LLM select best series from candidates
    if verbose:
        print("  Selecting best series...")
    result = select_best_series(query, candidates)

    if verbose:
        print(f"  Selected: {result.get('series', [])}")

    # Ensure all expected fields exist
    result.setdefault('search_terms', [])
    result.setdefault('show_yoy', False)
    result.setdefault('show_mom', False)
    result.setdefault('show_avg_annual', False)
    result.setdefault('combine_chart', False)
    result.setdefault('is_followup', False)
    result.setdefault('add_to_previous', False)
    result.setdefault('keep_previous_series', False)

    return result


# =============================================================================
# TEST
# =============================================================================

def test_rag():
    """Test RAG retrieval with sample queries."""
    test_queries = [
        "How is the economy for immigrants?",
        "How are restaurants doing?",
        "What's happening with women in the labor market?",
        "Is inflation coming down?",
        "Are we heading into a recession?",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        result = rag_query_plan(query, verbose=True)
        print(f"\nFinal plan:")
        print(f"  Series: {result['series']}")
        print(f"  Explanation: {result['explanation']}")


if __name__ == "__main__":
    test_rag()
