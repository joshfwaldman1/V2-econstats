"""
Zillow data integration for EconStats.

Fetches housing market data from Zillow Research's free public CSVs.
Data includes:
- ZORI (Zillow Observed Rent Index) - actual market rents
- ZHVI (Zillow Home Value Index) - home values
- Various cuts by metro, state, zip

CSV URLs: https://www.zillow.com/research/data/
"""

import csv
import io
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

# =============================================================================
# ZILLOW SERIES CATALOG
# =============================================================================

ZILLOW_SERIES = {
    # =============================================================================
    # NATIONAL HOME VALUES (ZHVI)
    # =============================================================================
    'zillow_zhvi_national': {
        'name': 'Zillow Home Value Index (National)',
        'description': 'Typical home value across the US for all homes (single-family, condo, co-op), smoothed and seasonally adjusted. Reflects median home values in the 35th-65th percentile range.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['home value', 'house price', 'zillow', 'zhvi', 'home price', 'median home value'],
    },
    'zillow_home_value_yoy': {
        'name': 'Zillow Home Value Growth (YoY %)',
        'description': 'Year-over-year percent change in typical US home value. Key indicator of housing market appreciation or depreciation trends nationwide.',
        'derived_from': 'zillow_zhvi_national',
        'measure_type': 'nominal',
        'change_type': 'yoy',
        'units': 'percent',
        'frequency': 'monthly',
        'keywords': ['home price growth', 'house price inflation', 'housing appreciation', 'home value change'],
    },
    'zillow_zhvi_sfr': {
        'name': 'Zillow Home Value Index - Single Family',
        'description': 'Typical home value for single-family residences only across the US. Excludes condos and co-ops. Better indicator for detached housing market trends.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfr_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['single family', 'detached home', 'sfr', 'house value', 'single family home price'],
    },
    'zillow_zhvi_condo': {
        'name': 'Zillow Home Value Index - Condo/Co-op',
        'description': 'Typical home value for condominiums and co-ops across the US. Tracks apartment-style ownership market, often different dynamics than single-family homes.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_condo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['condo', 'condominium', 'co-op', 'apartment ownership', 'condo price'],
    },
    'zillow_zhvi_top_tier': {
        'name': 'Zillow Home Value Index - Top Tier',
        'description': 'Typical home value for luxury/high-end homes in the 65th-95th percentile. Tracks upscale housing market which often leads or lags the broader market differently.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.67_1.0_sm_sa_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['luxury homes', 'high end', 'top tier', 'expensive homes', 'upscale housing', 'premium real estate'],
    },
    'zillow_zhvi_bottom_tier': {
        'name': 'Zillow Home Value Index - Bottom Tier',
        'description': 'Typical home value for starter/affordable homes in the 5th-35th percentile. Key indicator for first-time homebuyer affordability and entry-level housing market.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.0_0.33_sm_sa_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['starter homes', 'affordable homes', 'bottom tier', 'entry level', 'first time buyer', 'affordable housing'],
    },

    # =============================================================================
    # NATIONAL RENTS (ZORI)
    # =============================================================================
    'zillow_zori_national': {
        'name': 'Zillow Observed Rent Index (National)',
        'description': 'Typical observed market rent across the US for all rental properties, smoothed and seasonally adjusted. More timely than CPI rent, reflects actual asking rents.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['rent', 'rental', 'apartment', 'zillow', 'market rent', 'asking rent', 'zori'],
    },
    'zillow_rent_yoy': {
        'name': 'Zillow Rent Growth (YoY %)',
        'description': 'Year-over-year percent change in typical US market rent. Leading indicator of CPI shelter inflation, typically leads CPI rent by 6-12 months.',
        'derived_from': 'zillow_zori_national',
        'measure_type': 'nominal',
        'change_type': 'yoy',
        'units': 'percent',
        'frequency': 'monthly',
        'keywords': ['rent inflation', 'rent growth', 'rental prices', 'shelter inflation', 'housing costs'],
    },

    # =============================================================================
    # MARKET METRICS - INVENTORY & ACTIVITY
    # =============================================================================
    'zillow_inventory': {
        'name': 'Zillow For-Sale Inventory (National)',
        'description': 'Count of unique active listings nationwide at any time during the month. Key supply indicator - low inventory drives prices up, high inventory cools market.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/for_sale_inventory/Metro_for_sale_inventory_uc_sfrcondo_sm_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'count',
        'frequency': 'monthly',
        'keywords': ['inventory', 'listings', 'for sale', 'housing supply', 'available homes', 'active listings'],
    },
    'zillow_new_listings': {
        'name': 'Zillow New Listings (National)',
        'description': 'Count of new listings that came on market during the month nationwide. Measures seller activity and fresh supply entering the market.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/new_listings/Metro_new_listings_uc_sfrcondo_sm_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'count',
        'frequency': 'monthly',
        'keywords': ['new listings', 'fresh inventory', 'seller activity', 'homes for sale', 'new supply'],
    },
    'zillow_days_to_pending': {
        'name': 'Zillow Days to Pending (National)',
        'description': 'Median days from listing to pending status nationwide. Key market speed indicator - fewer days means hotter market with faster sales.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/median_days_to_pending/Metro_median_days_to_pending_uc_sfrcondo_sm_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'days',
        'frequency': 'monthly',
        'keywords': ['days on market', 'days to pending', 'market speed', 'how fast homes sell', 'time to sell'],
    },
    'zillow_sale_to_list': {
        'name': 'Zillow Sale-to-List Ratio (National)',
        'description': 'Ratio of sale price to list price nationwide (as percentage). Above 100% means bidding wars, below 100% means price cuts. Key demand indicator.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/sale_to_list/Metro_sale_to_list_uc_sfrcondo_sm_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'percent',
        'frequency': 'monthly',
        'keywords': ['sale to list', 'bidding wars', 'price cuts', 'over asking', 'under asking', 'offer price'],
    },
    'zillow_median_list_price': {
        'name': 'Zillow Median List Price (National)',
        'description': 'Median asking price for homes listed for sale nationwide. Reflects seller expectations and differs from actual sale prices and home value indices.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/median_list_price/Metro_median_list_price_uc_sfrcondo_sm_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['list price', 'asking price', 'listing price', 'home prices', 'for sale price'],
    },
    'zillow_median_sale_price': {
        'name': 'Zillow Median Sale Price (National)',
        'description': 'Median actual sale price for homes sold nationwide. Reflects real transaction prices, differs from list price and home value index.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/median_sale_price/Metro_median_sale_price_uc_sfrcondo_sm_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['sale price', 'sold price', 'transaction price', 'actual price', 'closing price'],
    },

    # =============================================================================
    # REGIONAL HOME VALUES - TOP METROS
    # =============================================================================
    'zillow_zhvi_nyc': {
        'name': 'Zillow Home Value Index - New York City Metro',
        'description': 'Typical home value in the New York-Newark-Jersey City metro area. Largest US housing market, includes Manhattan, Brooklyn, NJ suburbs.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'New York',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['new york', 'nyc', 'manhattan', 'brooklyn', 'new jersey', 'metro nyc', 'tri-state'],
    },
    'zillow_zhvi_la': {
        'name': 'Zillow Home Value Index - Los Angeles Metro',
        'description': 'Typical home value in the Los Angeles-Long Beach-Anaheim metro area. Second largest US market, includes Orange County and LA suburbs.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Los Angeles',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['los angeles', 'la', 'socal', 'southern california', 'orange county', 'long beach'],
    },
    'zillow_zhvi_chicago': {
        'name': 'Zillow Home Value Index - Chicago Metro',
        'description': 'Typical home value in the Chicago-Naperville-Elgin metro area. Third largest US market, Midwest housing hub.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Chicago',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['chicago', 'illinois', 'midwest', 'chicagoland', 'naperville'],
    },
    'zillow_zhvi_dallas': {
        'name': 'Zillow Home Value Index - Dallas Metro',
        'description': 'Typical home value in the Dallas-Fort Worth-Arlington metro area. Fourth largest US market, major Texas housing hub with strong growth.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Dallas',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['dallas', 'dfw', 'fort worth', 'texas', 'metroplex', 'arlington'],
    },
    'zillow_zhvi_houston': {
        'name': 'Zillow Home Value Index - Houston Metro',
        'description': 'Typical home value in the Houston-The Woodlands-Sugar Land metro area. Fifth largest US market, energy sector hub.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Houston',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['houston', 'texas', 'energy', 'the woodlands', 'sugar land', 'gulf coast'],
    },
    'zillow_zhvi_dc': {
        'name': 'Zillow Home Value Index - Washington DC Metro',
        'description': 'Typical home value in the Washington-Arlington-Alexandria metro area. Government and tech hub, includes Northern Virginia and Maryland suburbs.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Washington',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['washington dc', 'dc', 'dmv', 'northern virginia', 'nova', 'maryland', 'arlington'],
    },
    'zillow_zhvi_miami': {
        'name': 'Zillow Home Value Index - Miami Metro',
        'description': 'Typical home value in the Miami-Fort Lauderdale-Pompano Beach metro area. Major Florida market with international buyer influence.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Miami',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['miami', 'south florida', 'fort lauderdale', 'florida', 'pompano beach', 'broward'],
    },
    'zillow_zhvi_phoenix': {
        'name': 'Zillow Home Value Index - Phoenix Metro',
        'description': 'Typical home value in the Phoenix-Mesa-Chandler metro area. Fast-growing Sunbelt market with significant price volatility.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Phoenix',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['phoenix', 'arizona', 'az', 'mesa', 'chandler', 'scottsdale', 'sunbelt'],
    },
    'zillow_zhvi_atlanta': {
        'name': 'Zillow Home Value Index - Atlanta Metro',
        'description': 'Typical home value in the Atlanta-Sandy Springs-Alpharetta metro area. Major Southeast hub with strong corporate presence.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Atlanta',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['atlanta', 'georgia', 'southeast', 'sandy springs', 'alpharetta', 'buckhead'],
    },
    'zillow_zhvi_sf': {
        'name': 'Zillow Home Value Index - San Francisco Metro',
        'description': 'Typical home value in the San Francisco-Oakland-Berkeley metro area. High-cost tech hub market, extreme affordability challenges.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'San Francisco',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['san francisco', 'sf', 'bay area', 'oakland', 'berkeley', 'silicon valley', 'tech'],
    },
    'zillow_zhvi_boston': {
        'name': 'Zillow Home Value Index - Boston Metro',
        'description': 'Typical home value in the Boston-Cambridge-Newton metro area. Northeast tech and education hub with high home values.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Boston',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['boston', 'massachusetts', 'cambridge', 'newton', 'new england', 'biotech'],
    },
    'zillow_zhvi_seattle': {
        'name': 'Zillow Home Value Index - Seattle Metro',
        'description': 'Typical home value in the Seattle-Tacoma-Bellevue metro area. Pacific Northwest tech hub with Amazon/Microsoft influence.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Seattle',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['seattle', 'washington', 'pnw', 'tacoma', 'bellevue', 'puget sound', 'amazon'],
    },
    'zillow_zhvi_denver': {
        'name': 'Zillow Home Value Index - Denver Metro',
        'description': 'Typical home value in the Denver-Aurora-Centennial metro area. Mountain West hub with strong in-migration and outdoor appeal.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Denver',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['denver', 'colorado', 'aurora', 'boulder', 'front range', 'mountain west'],
    },
    'zillow_zhvi_tampa': {
        'name': 'Zillow Home Value Index - Tampa Metro',
        'description': 'Typical home value in the Tampa-St. Petersburg-Clearwater metro area. Florida Gulf Coast market with retiree and remote worker appeal.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'Tampa',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['tampa', 'st petersburg', 'clearwater', 'florida', 'gulf coast', 'tampa bay'],
    },
    'zillow_zhvi_san_diego': {
        'name': 'Zillow Home Value Index - San Diego Metro',
        'description': 'Typical home value in the San Diego-Chula Vista-Carlsbad metro area. Southern California coastal market with military and biotech presence.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'metro',
        'region_filter': 'San Diego',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['san diego', 'california', 'socal', 'chula vista', 'carlsbad', 'coastal'],
    },

    # =============================================================================
    # REGIONAL RENTS - TOP METROS
    # =============================================================================
    'zillow_zori_nyc': {
        'name': 'Zillow Rent Index - New York City Metro',
        'description': 'Typical market rent in the New York-Newark-Jersey City metro area. Highest rent market in the US, key indicator of urban rental trends.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'metro',
        'region_filter': 'New York',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['new york rent', 'nyc rent', 'manhattan rent', 'brooklyn rent', 'apartment rent nyc'],
    },
    'zillow_zori_la': {
        'name': 'Zillow Rent Index - Los Angeles Metro',
        'description': 'Typical market rent in the Los Angeles-Long Beach-Anaheim metro area. Second largest rental market, rent-controlled market dynamics.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'metro',
        'region_filter': 'Los Angeles',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['los angeles rent', 'la rent', 'socal rent', 'orange county rent', 'apartment rent la'],
    },
    'zillow_zori_sf': {
        'name': 'Zillow Rent Index - San Francisco Metro',
        'description': 'Typical market rent in the San Francisco-Oakland-Berkeley metro area. Among highest rents in US, sensitive to tech sector employment.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'metro',
        'region_filter': 'San Francisco',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['san francisco rent', 'sf rent', 'bay area rent', 'oakland rent', 'tech rent'],
    },
    'zillow_zori_miami': {
        'name': 'Zillow Rent Index - Miami Metro',
        'description': 'Typical market rent in the Miami-Fort Lauderdale-Pompano Beach metro area. Fast-growing rental market with remote worker influx.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'metro',
        'region_filter': 'Miami',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['miami rent', 'south florida rent', 'fort lauderdale rent', 'florida rent', 'beach rent'],
    },
    'zillow_zori_seattle': {
        'name': 'Zillow Rent Index - Seattle Metro',
        'description': 'Typical market rent in the Seattle-Tacoma-Bellevue metro area. Tech-driven rental market with significant new construction.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'metro',
        'region_filter': 'Seattle',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['seattle rent', 'washington rent', 'bellevue rent', 'puget sound rent', 'amazon rent'],
    },
    'zillow_zori_denver': {
        'name': 'Zillow Rent Index - Denver Metro',
        'description': 'Typical market rent in the Denver-Aurora-Centennial metro area. Fast-growing Mountain West rental market.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'metro',
        'region_filter': 'Denver',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['denver rent', 'colorado rent', 'aurora rent', 'boulder rent', 'mountain west rent'],
    },
    'zillow_zori_austin': {
        'name': 'Zillow Rent Index - Austin Metro',
        'description': 'Typical market rent in the Austin-Round Rock-Georgetown metro area. Tech boom market, experienced rapid rent growth and recent cooling.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'metro',
        'region_filter': 'Austin',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['austin rent', 'texas rent', 'round rock rent', 'tech rent austin', 'silicon hills'],
    },
    'zillow_zori_phoenix': {
        'name': 'Zillow Rent Index - Phoenix Metro',
        'description': 'Typical market rent in the Phoenix-Mesa-Chandler metro area. Sunbelt growth market with significant in-migration.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv',
        'geography': 'metro',
        'region_filter': 'Phoenix',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars',
        'frequency': 'monthly',
        'keywords': ['phoenix rent', 'arizona rent', 'mesa rent', 'scottsdale rent', 'sunbelt rent'],
    },

    # =============================================================================
    # AFFORDABILITY & SPECIALTY METRICS
    # =============================================================================
    'zillow_zhvi_per_sqft': {
        'name': 'Zillow Home Value per Square Foot (National)',
        'description': 'Typical home value per square foot across the US. Better comparability across different home sizes, useful for density and land value analysis.',
        'url': 'https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv',
        'geography': 'national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'dollars_per_sqft',
        'frequency': 'monthly',
        'keywords': ['price per square foot', 'cost per sqft', 'home value per sqft', 'land value', 'density'],
    },
    'zillow_price_to_rent': {
        'name': 'Zillow Price-to-Rent Ratio (Derived)',
        'description': 'Ratio of home values to annual rent. Key buy vs rent decision metric. High ratio favors renting, low ratio favors buying.',
        'derived_from': 'zillow_zhvi_national',
        'measure_type': 'nominal',
        'change_type': 'level',
        'units': 'ratio',
        'frequency': 'monthly',
        'keywords': ['price to rent', 'buy vs rent', 'rent vs buy', 'affordability ratio', 'housing affordability'],
    },
}

# Cache for fetched data (avoid repeated downloads)
_cache = {}
_cache_ttl = timedelta(hours=1)


def _fetch_csv(url: str) -> list:
    """Fetch and parse a CSV from Zillow."""
    cache_key = url
    now = datetime.now()

    # Check cache
    if cache_key in _cache:
        cached_data, cached_time = _cache[cache_key]
        if now - cached_time < _cache_ttl:
            return cached_data

    try:
        req = Request(url, headers={'User-Agent': 'EconStats/1.0'})
        with urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)
            _cache[cache_key] = (rows, now)
            return rows
    except URLError as e:
        print(f"[Zillow] Error fetching {url}: {e}")
        return []


def _parse_zillow_metro_csv(rows: list, target_region: str = "United States") -> tuple:
    """
    Parse Zillow metro-level CSV and extract national data.

    Zillow CSVs have format:
    RegionID, SizeRank, RegionName, RegionType, StateName, 2015-01-31, 2015-02-28, ...

    Returns: (dates, values) where dates are datetime objects
    """
    if not rows:
        return [], []

    header = rows[0]

    # Find date columns (format: YYYY-MM-DD)
    date_cols = []
    for i, col in enumerate(header):
        if len(col) == 10 and col[4] == '-' and col[7] == '-':
            try:
                datetime.strptime(col, '%Y-%m-%d')
                date_cols.append((i, col))
            except ValueError:
                continue

    if not date_cols:
        print("[Zillow] No date columns found in CSV")
        return [], []

    # Find the target region row (United States for national)
    target_row = None
    for row in rows[1:]:
        if len(row) > 2:
            region_name = row[2] if len(row) > 2 else ""
            if target_region.lower() in region_name.lower():
                target_row = row
                break

    if not target_row:
        print(f"[Zillow] Region '{target_region}' not found in CSV")
        return [], []

    # Extract dates and values
    dates = []
    values = []
    for col_idx, date_str in date_cols:
        if col_idx < len(target_row):
            val_str = target_row[col_idx]
            if val_str and val_str.strip():
                try:
                    val = float(val_str)
                    dates.append(datetime.strptime(date_str, '%Y-%m-%d'))
                    values.append(val)
                except ValueError:
                    continue

    return dates, values


def _calculate_yoy(dates: list, values: list) -> tuple:
    """Calculate year-over-year percent change."""
    if len(dates) < 13:
        return [], []

    # Create lookup by (year, month)
    by_month = {}
    for d, v in zip(dates, values):
        by_month[(d.year, d.month)] = v

    yoy_dates = []
    yoy_values = []

    for d, v in zip(dates, values):
        prev_key = (d.year - 1, d.month)
        if prev_key in by_month:
            prev_v = by_month[prev_key]
            if prev_v and prev_v != 0:
                pct_change = ((v - prev_v) / prev_v) * 100
                yoy_dates.append(d)
                yoy_values.append(round(pct_change, 2))

    return yoy_dates, yoy_values


def get_zillow_series(series_key: str) -> tuple:
    """
    Fetch a Zillow series.

    Args:
        series_key: One of the keys in ZILLOW_SERIES

    Returns:
        (dates, values, info) tuple compatible with FRED format
        - dates: list of 'YYYY-MM-DD' strings
        - values: list of float values
        - info: dict with series metadata
    """
    if series_key not in ZILLOW_SERIES:
        return [], [], {'error': f"Unknown Zillow series: {series_key}"}

    series_info = ZILLOW_SERIES[series_key]

    # Handle derived series (YoY calculations or other derived metrics)
    if 'derived_from' in series_info:
        base_key = series_info['derived_from']
        base_dates, base_values, base_info = get_zillow_series(base_key)

        if not base_dates:
            return [], [], {'error': f"Could not fetch base series {base_key}"}

        # Convert string dates back to datetime for calculation
        dt_dates = [datetime.strptime(d, '%Y-%m-%d') for d in base_dates]

        # Handle price-to-rent ratio specially
        if series_key == 'zillow_price_to_rent':
            # Fetch rent data too
            rent_dates, rent_values, rent_info = get_zillow_series('zillow_zori_national')
            if not rent_dates:
                return [], [], {'error': 'Could not fetch rent data for price-to-rent calculation'}

            # Convert rent dates to datetime
            rent_dt_dates = [datetime.strptime(d, '%Y-%m-%d') for d in rent_dates]

            # Create lookup by (year, month) for rent
            rent_by_month = {}
            for d, v in zip(rent_dt_dates, rent_values):
                rent_by_month[(d.year, d.month)] = v

            # Calculate price-to-rent ratio (home value / annual rent)
            ptr_dates = []
            ptr_values = []
            for d, home_val in zip(dt_dates, base_values):
                key = (d.year, d.month)
                if key in rent_by_month and rent_by_month[key] > 0:
                    annual_rent = rent_by_month[key] * 12
                    ratio = home_val / annual_rent
                    ptr_dates.append(d)
                    ptr_values.append(round(ratio, 2))

            date_strings = [d.strftime('%Y-%m-%d') for d in ptr_dates]

            info = {
                'id': series_key,
                'title': series_info['name'],
                'description': series_info['description'],
                'units': series_info['units'],
                'frequency': series_info['frequency'],
                'source': 'Zillow Research',
                'measure_type': series_info['measure_type'],
                'change_type': series_info['change_type'],
            }

            return date_strings, ptr_values, info

        # Standard YoY calculation for other derived series
        yoy_dates, yoy_values = _calculate_yoy(dt_dates, base_values)

        # Convert back to strings
        date_strings = [d.strftime('%Y-%m-%d') for d in yoy_dates]

        info = {
            'id': series_key,
            'title': series_info['name'],
            'description': series_info['description'],
            'units': series_info['units'],
            'frequency': series_info['frequency'],
            'source': 'Zillow Research',
            'measure_type': series_info['measure_type'],
            'change_type': series_info['change_type'],
        }

        return date_strings, yoy_values, info

    # Fetch raw CSV data
    url = series_info.get('url')
    if not url:
        return [], [], {'error': f"No URL for series {series_key}"}

    rows = _fetch_csv(url)
    if not rows:
        return [], [], {'error': f"Could not fetch data from Zillow"}

    # Determine target region - use region_filter for metro-level data, "United States" for national
    geography = series_info.get('geography', 'national')
    if geography == 'metro' and 'region_filter' in series_info:
        target_region = series_info['region_filter']
    else:
        target_region = "United States"

    dates, values = _parse_zillow_metro_csv(rows, target_region=target_region)

    if not dates:
        return [], [], {'error': f"Could not parse Zillow data for region: {target_region}"}

    # Convert dates to strings
    date_strings = [d.strftime('%Y-%m-%d') for d in dates]

    info = {
        'id': series_key,
        'title': series_info['name'],
        'description': series_info['description'],
        'units': series_info['units'],
        'frequency': series_info['frequency'],
        'source': 'Zillow Research',
        'measure_type': series_info['measure_type'],
        'change_type': series_info['change_type'],
    }

    return date_strings, values, info


def search_zillow_series(query: str) -> list:
    """
    Search for Zillow series matching a query.

    Returns list of matching series keys.
    """
    query_lower = query.lower()
    matches = []

    for key, info in ZILLOW_SERIES.items():
        # Check name, description, and keywords
        searchable = (
            info['name'].lower() + ' ' +
            info.get('description', '').lower() + ' ' +
            ' '.join(info.get('keywords', []))
        )

        # Score by keyword matches
        score = 0
        for word in query_lower.split():
            if word in searchable:
                score += 1

        if score > 0:
            matches.append((key, score, info['name']))

    # Sort by score descending
    matches.sort(key=lambda x: -x[1])

    return [m[0] for m in matches]


def get_available_series() -> dict:
    """Return all available Zillow series for catalog display."""
    return ZILLOW_SERIES.copy()


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("Testing Zillow data fetch...")

    # Test ZORI
    print("\n1. Testing ZORI (National Rent Index):")
    dates, values, info = get_zillow_series('zillow_zori_national')
    if dates:
        print(f"   Got {len(dates)} observations")
        print(f"   Latest: {dates[-1]} = ${values[-1]:,.0f}")
        print(f"   Earliest: {dates[0]} = ${values[0]:,.0f}")
    else:
        print(f"   Error: {info.get('error', 'Unknown error')}")

    # Test ZHVI
    print("\n2. Testing ZHVI (National Home Value Index):")
    dates, values, info = get_zillow_series('zillow_zhvi_national')
    if dates:
        print(f"   Got {len(dates)} observations")
        print(f"   Latest: {dates[-1]} = ${values[-1]:,.0f}")
    else:
        print(f"   Error: {info.get('error', 'Unknown error')}")

    # Test YoY rent
    print("\n3. Testing Rent YoY:")
    dates, values, info = get_zillow_series('zillow_rent_yoy')
    if dates:
        print(f"   Got {len(dates)} observations")
        print(f"   Latest: {dates[-1]} = {values[-1]:.1f}%")
    else:
        print(f"   Error: {info.get('error', 'Unknown error')}")

    # Test search
    print("\n4. Testing search for 'rent':")
    matches = search_zillow_series("rent")
    print(f"   Matches: {matches}")


# =============================================================================
# NARRATIVE SYNTHESIS (Economist-style interpretation)
# =============================================================================

def synthesize_housing_narrative(
    rent_value: Optional[float] = None,
    rent_yoy: Optional[float] = None,
    home_value: Optional[float] = None,
    home_value_yoy: Optional[float] = None,
) -> Optional[str]:
    """
    Synthesize housing data into a coherent narrative paragraph.

    Instead of listing numbers, describes what the housing picture looks like
    with context about why it matters for the economy.

    Args:
        rent_value: Current national rent level ($/month)
        rent_yoy: Rent year-over-year change (%)
        home_value: Current national home value ($)
        home_value_yoy: Home value year-over-year change (%)

    Returns:
        Human-readable narrative about housing conditions
    """
    parts = []

    # Rent narrative
    if rent_yoy is not None:
        if rent_yoy < 0:
            parts.append(
                f"Market rents are actually falling ({rent_yoy:.1f}% YoY), "
                "which should pull CPI shelter inflation down over the next 12-18 months "
                "as the official measure catches up to reality."
            )
        elif rent_yoy < 2:
            parts.append(
                f"Rent growth has cooled to just {rent_yoy:.1f}% YoY—back to pre-pandemic norms. "
                "This is good news for inflation: shelter is the largest CPI component, "
                "and market rents lead the official measure by about a year."
            )
        elif rent_yoy < 5:
            parts.append(
                f"Rents are rising at a moderate {rent_yoy:.1f}% YoY pace. "
                "That's elevated but not alarming—shelter inflation in CPI "
                "should continue its gradual descent."
            )
        else:
            parts.append(
                f"Rent growth remains hot at {rent_yoy:.1f}% YoY, "
                "which will keep CPI shelter inflation elevated for months to come. "
                "The Fed watches this closely."
            )

    # Home value narrative
    if home_value_yoy is not None:
        if home_value_yoy < 0:
            parts.append(
                f"Home prices are declining ({home_value_yoy:.1f}% YoY), "
                "a rare event that typically requires either a recession or a surge in inventory. "
                "Homeowners with 3% mortgages are still reluctant to sell into a 7% rate environment."
            )
        elif home_value_yoy < 3:
            parts.append(
                f"Home prices are essentially flat ({home_value_yoy:.1f}% YoY). "
                "High mortgage rates have frozen the market: few can afford to buy, "
                "and homeowners with cheap pandemic-era mortgages have no reason to sell."
            )
        elif home_value_yoy < 6:
            parts.append(
                f"Home prices continue rising ({home_value_yoy:.1f}% YoY) despite high mortgage rates, "
                "driven by extremely low inventory. Existing homeowners won't sell their 3% mortgages, "
                "and new construction hasn't filled the gap."
            )
        else:
            parts.append(
                f"Home values are surging {home_value_yoy:.1f}% YoY—remarkable given 7%+ mortgage rates. "
                "The lock-in effect is acute: with so few willing to sell, "
                "any demand pushes prices sharply higher."
            )

    # Affordability context if we have both
    if rent_value is not None and home_value is not None:
        # Rough monthly mortgage payment at 7% on 80% LTV
        monthly_mortgage = (home_value * 0.8) * (0.07 / 12) / (1 - (1 + 0.07/12)**-360)
        if monthly_mortgage > rent_value * 1.5:
            parts.append(
                f"With typical mortgage payments around ${monthly_mortgage:,.0f}/month vs ${rent_value:,.0f} rent, "
                "buying is 50%+ more expensive than renting—an unusual situation that keeps many on the sidelines."
            )

    if not parts:
        return None

    return " ".join(parts)


def get_housing_narrative() -> Optional[str]:
    """
    Convenience function to fetch current Zillow data and synthesize narrative.

    Returns:
        Synthesized narrative about current housing conditions, or None on error.
    """
    # Fetch current data
    _, rent_values, rent_info = get_zillow_series('zillow_zori_national')
    _, rent_yoy_values, _ = get_zillow_series('zillow_rent_yoy')
    _, home_values, _ = get_zillow_series('zillow_zhvi_national')
    _, home_yoy_values, _ = get_zillow_series('zillow_home_value_yoy')

    # Get latest values
    rent_value = rent_values[-1] if rent_values else None
    rent_yoy = rent_yoy_values[-1] if rent_yoy_values else None
    home_value = home_values[-1] if home_values else None
    home_value_yoy = home_yoy_values[-1] if home_yoy_values else None

    return synthesize_housing_narrative(
        rent_value=rent_value,
        rent_yoy=rent_yoy,
        home_value=home_value,
        home_value_yoy=home_value_yoy,
    )
