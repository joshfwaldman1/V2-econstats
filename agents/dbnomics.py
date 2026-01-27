"""
DBnomics integration for EconStats - International economic data.

DBnomics aggregates data from 80+ providers including IMF, Eurostat, ECB, OECD, World Bank.
This adds international coverage that FRED doesn't have.

API: https://api.db.nomics.world/v22/
"""

import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from datetime import datetime, timedelta
from typing import Optional

# Cache to avoid excessive API calls
_cache: dict = {}
_cache_ttl = timedelta(minutes=30)

DBNOMICS_API = "https://api.db.nomics.world/v22"

# Curated international series with full DBnomics IDs
# Format: provider/dataset/series_code
#
# CRITICAL METADATA for apples-to-apples comparisons:
# - measure_type: "real" (inflation-adjusted) or "nominal" or "rate"
# - change_type: "yoy" (year-over-year), "qoq" (quarter-over-quarter), "level"
# - frequency: "annual", "quarterly", "monthly", "daily"
#
# COMPARISON RULES:
# - GDP: Must compare real with real, YoY with YoY
# - Inflation: YoY rates are standard
# - Unemployment: Levels (rates) are comparable
# - Interest rates: Levels are comparable
#
INTERNATIONAL_SERIES = {
    # === EUROZONE ===
    "eurozone_gdp": {
        "id": "Eurostat/namq_10_gdp/Q.CLV_PCH_SM.SCA.B1GQ.EA20",
        "name": "Eurozone GDP Growth (YoY)",
        "description": "Euro area real GDP growth, year-over-year",
        "keywords": ["eurozone", "euro area", "europe", "gdp", "eu"],
        "provider": "Eurostat",
        # Metadata for comparison validation
        "measure_type": "real",  # Chain-linked volumes = inflation-adjusted
        "change_type": "yoy",    # PCH_SM = same period previous year
        "frequency": "quarterly",
    },
    "eurozone_inflation": {
        "id": "Eurostat/prc_hicp_manr/M.RCH_A.CP00.EA",
        "name": "Eurozone Inflation (HICP)",
        "description": "Euro area harmonized CPI, year-over-year",
        "keywords": ["eurozone", "euro", "inflation", "hicp", "cpi", "europe"],
        "provider": "Eurostat",
        "measure_type": "rate",
        "change_type": "yoy",  # RCH_A = annual rate of change
        "frequency": "monthly",
    },
    "eurozone_unemployment": {
        "id": "Eurostat/une_rt_m/M.SA.TOTAL.PC_ACT.T.EA20",
        "name": "Eurozone Unemployment Rate",
        "description": "Euro area unemployment rate, seasonally adjusted",
        "keywords": ["eurozone", "unemployment", "europe", "jobs"],
        "provider": "Eurostat",
        "measure_type": "rate",
        "change_type": "level",  # It's a rate level, not a change
        "frequency": "monthly",
    },
    # === UK ===
    "uk_gdp": {
        "id": "IMF/WEO:2024-10/GBR.NGDP_RPCH.pcent_change",
        "name": "UK GDP Growth (YoY)",
        "description": "UK real GDP growth, year-over-year (IMF)",
        "keywords": ["uk", "britain", "british", "gdp", "england"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",  # RPCH = Real Percent Change
        "frequency": "annual",
    },
    "uk_inflation": {
        "id": "IMF/WEO:2024-10/GBR.PCPIPCH.pcent_change",
        "name": "UK Inflation (CPI)",
        "description": "UK CPI inflation, year-over-year (IMF)",
        "keywords": ["uk", "britain", "inflation", "cpi"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    # Note: Bank of England rate data not reliably available via DBnomics
    # The BOE provider has limited series; users should check FRED for BOEUKLTIR (UK long-term rate) instead
    # === JAPAN ===
    "japan_gdp": {
        "id": "IMF/WEO:2024-10/JPN.NGDP_RPCH.pcent_change",
        "name": "Japan GDP Growth (YoY)",
        "description": "Japan real GDP growth, year-over-year (IMF)",
        "keywords": ["japan", "japanese", "gdp", "asia"],
        "provider": "IMF",
        "measure_type": "real",  # RPCH = Real Percent Change
        "change_type": "yoy",
        "frequency": "annual",
    },
    "japan_inflation": {
        "id": "IMF/WEO:2024-10/JPN.PCPIPCH.pcent_change",
        "name": "Japan Inflation",
        "description": "Japan CPI inflation, year-over-year (IMF)",
        "keywords": ["japan", "inflation", "cpi"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    # === CHINA ===
    "china_gdp": {
        "id": "IMF/WEO:2024-10/CHN.NGDP_RPCH.pcent_change",
        "name": "China GDP Growth (YoY)",
        "description": "China real GDP growth, year-over-year (IMF)",
        "keywords": ["china", "chinese", "gdp", "asia"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "china_inflation": {
        "id": "IMF/WEO:2024-10/CHN.PCPIPCH.pcent_change",
        "name": "China Inflation",
        "description": "China CPI inflation, year-over-year (IMF)",
        "keywords": ["china", "inflation", "cpi"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    # === GERMANY ===
    "germany_gdp": {
        "id": "IMF/WEO:2024-10/DEU.NGDP_RPCH.pcent_change",
        "name": "Germany GDP Growth (YoY)",
        "description": "Germany real GDP growth, year-over-year",
        "keywords": ["germany", "german", "gdp", "europe"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "germany_unemployment": {
        "id": "Eurostat/une_rt_m/M.SA.TOTAL.PC_ACT.T.DE",
        "name": "Germany Unemployment Rate",
        "description": "Germany unemployment rate",
        "keywords": ["germany", "unemployment", "jobs"],
        "provider": "Eurostat",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "monthly",
    },
    # === CANADA ===
    "canada_gdp": {
        "id": "IMF/WEO:2024-10/CAN.NGDP_RPCH.pcent_change",
        "name": "Canada GDP Growth (YoY)",
        "description": "Canada real GDP growth, year-over-year",
        "keywords": ["canada", "canadian", "gdp"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    # === MEXICO ===
    "mexico_gdp": {
        "id": "IMF/WEO:2024-10/MEX.NGDP_RPCH.pcent_change",
        "name": "Mexico GDP Growth (YoY)",
        "description": "Mexico real GDP growth, year-over-year",
        "keywords": ["mexico", "mexican", "gdp"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    # === INDIA ===
    "india_gdp": {
        "id": "IMF/WEO:2024-10/IND.NGDP_RPCH.pcent_change",
        "name": "India GDP Growth (YoY)",
        "description": "India real GDP growth, year-over-year",
        "keywords": ["india", "indian", "gdp"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    # === BRAZIL ===
    "brazil_gdp": {
        "id": "IMF/WEO:2024-10/BRA.NGDP_RPCH.pcent_change",
        "name": "Brazil GDP Growth (YoY)",
        "description": "Brazil real GDP growth, year-over-year",
        "keywords": ["brazil", "brazilian", "gdp"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    # === ECB ===
    "ecb_rate": {
        "id": "ECB/FM/D.U2.EUR.4F.KR.MRR_FR.LEV",
        "name": "ECB Main Refinancing Rate",
        "description": "European Central Bank main policy rate",
        "keywords": ["ecb", "euro", "rate", "europe", "interest"],
        "provider": "ECB",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "daily",
    },

    # ==========================================================================
    # EXPANDED COVERAGE - Additional Countries (30+ new series)
    # ==========================================================================

    # === SOUTH KOREA ===
    "south_korea_gdp": {
        "id": "IMF/WEO:2024-10/KOR.NGDP_RPCH.pcent_change",
        "name": "South Korea GDP Growth (YoY)",
        "description": "South Korea real GDP growth, year-over-year. Key Asian economy and major exporter of electronics, automobiles, and semiconductors.",
        "keywords": ["south korea", "korea", "korean", "gdp", "asia", "asian tigers"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "south_korea_inflation": {
        "id": "IMF/WEO:2024-10/KOR.PCPIPCH.pcent_change",
        "name": "South Korea Inflation (CPI)",
        "description": "South Korea consumer price inflation, year-over-year. Tracks cost of living changes in this major Asian economy.",
        "keywords": ["south korea", "korea", "korean", "inflation", "cpi", "asia"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "south_korea_unemployment": {
        "id": "OECD/MEI/KOR.LRHUTTTT.STSA.M",
        "name": "South Korea Unemployment Rate",
        "description": "South Korea harmonized unemployment rate, seasonally adjusted. Monthly labor market indicator from OECD.",
        "keywords": ["south korea", "korea", "korean", "unemployment", "jobs", "labor"],
        "provider": "OECD",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "monthly",
    },
    "south_korea_industrial_production": {
        "id": "OECD/MEI/KOR.PRINTO01.GYSA.M",
        "name": "South Korea Industrial Production (YoY)",
        "description": "South Korea industrial production growth, year-over-year. Measures manufacturing and industrial output changes.",
        "keywords": ["south korea", "korea", "industrial production", "manufacturing", "output"],
        "provider": "OECD",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "monthly",
    },
    "south_korea_current_account": {
        "id": "IMF/WEO:2024-10/KOR.BCA_NGDPD.pcent_gdp",
        "name": "South Korea Current Account (% GDP)",
        "description": "South Korea current account balance as percent of GDP. Key indicator of trade and investment flows for this export-oriented economy.",
        "keywords": ["south korea", "korea", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === AUSTRALIA ===
    "australia_gdp": {
        "id": "IMF/WEO:2024-10/AUS.NGDP_RPCH.pcent_change",
        "name": "Australia GDP Growth (YoY)",
        "description": "Australia real GDP growth, year-over-year. Major commodity exporter closely tied to Chinese demand.",
        "keywords": ["australia", "australian", "gdp", "oceania", "commodities"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "australia_inflation": {
        "id": "IMF/WEO:2024-10/AUS.PCPIPCH.pcent_change",
        "name": "Australia Inflation (CPI)",
        "description": "Australia consumer price inflation, year-over-year. Tracks cost of living changes and RBA policy direction.",
        "keywords": ["australia", "australian", "inflation", "cpi", "rba"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "australia_unemployment": {
        "id": "IMF/WEO:2024-10/AUS.LUR.pcent_total_labor_force",
        "name": "Australia Unemployment Rate",
        "description": "Australia unemployment rate as percent of labor force. Key labor market indicator for this commodity-driven economy.",
        "keywords": ["australia", "australian", "unemployment", "jobs", "labor"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },
    "australia_current_account": {
        "id": "IMF/WEO:2024-10/AUS.BCA_NGDPD.pcent_gdp",
        "name": "Australia Current Account (% GDP)",
        "description": "Australia current account balance as percent of GDP. Reflects commodity export strength and investment flows.",
        "keywords": ["australia", "australian", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === CANADA (expanded) ===
    "canada_inflation": {
        "id": "IMF/WEO:2024-10/CAN.PCPIPCH.pcent_change",
        "name": "Canada Inflation (CPI)",
        "description": "Canada consumer price inflation, year-over-year. Influences Bank of Canada monetary policy decisions.",
        "keywords": ["canada", "canadian", "inflation", "cpi", "boc", "bank of canada"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "canada_unemployment": {
        "id": "OECD/MEI/CAN.LRHUTTTT.STSA.M",
        "name": "Canada Unemployment Rate",
        "description": "Canada harmonized unemployment rate, seasonally adjusted. Monthly labor market indicator.",
        "keywords": ["canada", "canadian", "unemployment", "jobs", "labor"],
        "provider": "OECD",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "monthly",
    },
    "canada_industrial_production": {
        "id": "OECD/MEI/CAN.PRINTO01.GYSA.M",
        "name": "Canada Industrial Production (YoY)",
        "description": "Canada industrial production growth, year-over-year. Measures manufacturing and resource sector output.",
        "keywords": ["canada", "canadian", "industrial production", "manufacturing", "output"],
        "provider": "OECD",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "monthly",
    },
    "canada_current_account": {
        "id": "IMF/WEO:2024-10/CAN.BCA_NGDPD.pcent_gdp",
        "name": "Canada Current Account (% GDP)",
        "description": "Canada current account balance as percent of GDP. Reflects energy exports and trade with US.",
        "keywords": ["canada", "canadian", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === MEXICO (expanded) ===
    "mexico_inflation": {
        "id": "IMF/WEO:2024-10/MEX.PCPIPCH.pcent_change",
        "name": "Mexico Inflation (CPI)",
        "description": "Mexico consumer price inflation, year-over-year. Key indicator for Banxico monetary policy.",
        "keywords": ["mexico", "mexican", "inflation", "cpi", "banxico"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "mexico_unemployment": {
        "id": "IMF/WEO:2024-10/MEX.LUR.pcent_total_labor_force",
        "name": "Mexico Unemployment Rate",
        "description": "Mexico unemployment rate as percent of labor force. Labor market conditions in this major US trading partner.",
        "keywords": ["mexico", "mexican", "unemployment", "jobs", "labor"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },
    "mexico_current_account": {
        "id": "IMF/WEO:2024-10/MEX.BCA_NGDPD.pcent_gdp",
        "name": "Mexico Current Account (% GDP)",
        "description": "Mexico current account balance as percent of GDP. Reflects manufacturing exports and remittances.",
        "keywords": ["mexico", "mexican", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === INDIA (expanded) ===
    "india_inflation": {
        "id": "IMF/WEO:2024-10/IND.PCPIPCH.pcent_change",
        "name": "India Inflation (CPI)",
        "description": "India consumer price inflation, year-over-year. Key indicator for RBI monetary policy in this fast-growing economy.",
        "keywords": ["india", "indian", "inflation", "cpi", "rbi"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "india_unemployment": {
        "id": "IMF/WEO:2024-10/IND.LUR.pcent_total_labor_force",
        "name": "India Unemployment Rate",
        "description": "India unemployment rate as percent of labor force. Labor market conditions in the world's most populous nation.",
        "keywords": ["india", "indian", "unemployment", "jobs", "labor"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },
    "india_current_account": {
        "id": "IMF/WEO:2024-10/IND.BCA_NGDPD.pcent_gdp",
        "name": "India Current Account (% GDP)",
        "description": "India current account balance as percent of GDP. Reflects services exports and import dependency.",
        "keywords": ["india", "indian", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === BRAZIL (expanded) ===
    "brazil_inflation": {
        "id": "IMF/WEO:2024-10/BRA.PCPIPCH.pcent_change",
        "name": "Brazil Inflation (CPI)",
        "description": "Brazil consumer price inflation, year-over-year. Key indicator for BCB monetary policy in Latin America's largest economy.",
        "keywords": ["brazil", "brazilian", "inflation", "cpi", "bcb", "latin america"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "brazil_unemployment": {
        "id": "OECD/MEI/BRA.LRUNTTTT.STSA.M",
        "name": "Brazil Unemployment Rate",
        "description": "Brazil unemployment rate, seasonally adjusted. Monthly labor market indicator for Latin America's largest economy.",
        "keywords": ["brazil", "brazilian", "unemployment", "jobs", "labor", "latin america"],
        "provider": "OECD",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "monthly",
    },
    "brazil_industrial_production": {
        "id": "OECD/MEI/BRA.PRINTO01.GYSA.M",
        "name": "Brazil Industrial Production (YoY)",
        "description": "Brazil industrial production growth, year-over-year. Measures manufacturing output in this major emerging market.",
        "keywords": ["brazil", "brazilian", "industrial production", "manufacturing", "output"],
        "provider": "OECD",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "monthly",
    },
    "brazil_current_account": {
        "id": "IMF/WEO:2024-10/BRA.BCA_NGDPD.pcent_gdp",
        "name": "Brazil Current Account (% GDP)",
        "description": "Brazil current account balance as percent of GDP. Reflects commodity exports and capital flows.",
        "keywords": ["brazil", "brazilian", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === EUROZONE (expanded) ===
    "eurozone_industrial_production": {
        "id": "Eurostat/sts_inpr_m/M.SCA.I21.B-D.EA20",
        "name": "Eurozone Industrial Production (YoY)",
        "description": "Euro area industrial production index, seasonally and calendar adjusted. Key indicator of manufacturing health across the eurozone.",
        "keywords": ["eurozone", "euro area", "industrial production", "manufacturing", "europe"],
        "provider": "Eurostat",
        "measure_type": "index",
        "change_type": "level",
        "frequency": "monthly",
    },
    "eurozone_current_account": {
        "id": "ECB/BOP/M.I8.S1.S1.CA.D.FA._Z._Z._Z.EUR._T._X.N",
        "name": "Eurozone Current Account Balance",
        "description": "Euro area current account balance. Tracks trade in goods, services, and investment income flows.",
        "keywords": ["eurozone", "euro area", "current account", "trade", "balance of payments"],
        "provider": "ECB",
        "measure_type": "nominal",
        "change_type": "level",
        "frequency": "monthly",
    },

    # === UK (expanded) ===
    "uk_unemployment": {
        "id": "IMF/WEO:2024-10/GBR.LUR.pcent_total_labor_force",
        "name": "UK Unemployment Rate",
        "description": "UK unemployment rate as percent of labor force. Labor market conditions post-Brexit.",
        "keywords": ["uk", "britain", "british", "england", "unemployment", "jobs"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },
    "uk_current_account": {
        "id": "IMF/WEO:2024-10/GBR.BCA_NGDPD.pcent_gdp",
        "name": "UK Current Account (% GDP)",
        "description": "UK current account balance as percent of GDP. Reflects trade and financial services flows post-Brexit.",
        "keywords": ["uk", "britain", "british", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === JAPAN (expanded) ===
    "japan_unemployment": {
        "id": "IMF/WEO:2024-10/JPN.LUR.pcent_total_labor_force",
        "name": "Japan Unemployment Rate",
        "description": "Japan unemployment rate as percent of labor force. Traditionally low due to tight labor market and demographics.",
        "keywords": ["japan", "japanese", "unemployment", "jobs", "labor"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },
    "japan_industrial_production": {
        "id": "OECD/MEI/JPN.PRINTO01.GYSA.M",
        "name": "Japan Industrial Production (YoY)",
        "description": "Japan industrial production growth, year-over-year. Key indicator for this major manufacturing economy.",
        "keywords": ["japan", "japanese", "industrial production", "manufacturing", "output"],
        "provider": "OECD",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "monthly",
    },
    "japan_current_account": {
        "id": "IMF/WEO:2024-10/JPN.BCA_NGDPD.pcent_gdp",
        "name": "Japan Current Account (% GDP)",
        "description": "Japan current account balance as percent of GDP. Historically strong surplus driven by investment income.",
        "keywords": ["japan", "japanese", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === CHINA (expanded) ===
    "china_unemployment": {
        "id": "IMF/WEO:2024-10/CHN.LUR.pcent_total_labor_force",
        "name": "China Unemployment Rate",
        "description": "China unemployment rate as percent of labor force. Official surveyed unemployment rate.",
        "keywords": ["china", "chinese", "unemployment", "jobs", "labor"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },
    "china_current_account": {
        "id": "IMF/WEO:2024-10/CHN.BCA_NGDPD.pcent_gdp",
        "name": "China Current Account (% GDP)",
        "description": "China current account balance as percent of GDP. Reflects trade surplus and capital flows.",
        "keywords": ["china", "chinese", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === GERMANY (expanded) ===
    "germany_inflation": {
        "id": "IMF/WEO:2024-10/DEU.PCPIPCH.pcent_change",
        "name": "Germany Inflation (CPI)",
        "description": "Germany consumer price inflation, year-over-year. Key indicator for Europe's largest economy.",
        "keywords": ["germany", "german", "inflation", "cpi", "europe"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "germany_industrial_production": {
        "id": "OECD/MEI/DEU.PRINTO01.GYSA.M",
        "name": "Germany Industrial Production (YoY)",
        "description": "Germany industrial production growth, year-over-year. Critical indicator for Europe's manufacturing powerhouse.",
        "keywords": ["germany", "german", "industrial production", "manufacturing", "output"],
        "provider": "OECD",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "monthly",
    },
    "germany_current_account": {
        "id": "IMF/WEO:2024-10/DEU.BCA_NGDPD.pcent_gdp",
        "name": "Germany Current Account (% GDP)",
        "description": "Germany current account balance as percent of GDP. Chronically high surplus from export strength.",
        "keywords": ["germany", "german", "current account", "trade", "balance of payments"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === FRANCE ===
    "france_gdp": {
        "id": "IMF/WEO:2024-10/FRA.NGDP_RPCH.pcent_change",
        "name": "France GDP Growth (YoY)",
        "description": "France real GDP growth, year-over-year. Second largest eurozone economy.",
        "keywords": ["france", "french", "gdp", "europe"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "france_inflation": {
        "id": "IMF/WEO:2024-10/FRA.PCPIPCH.pcent_change",
        "name": "France Inflation (CPI)",
        "description": "France consumer price inflation, year-over-year.",
        "keywords": ["france", "french", "inflation", "cpi", "europe"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "france_unemployment": {
        "id": "Eurostat/une_rt_m/M.SA.TOTAL.PC_ACT.T.FR",
        "name": "France Unemployment Rate",
        "description": "France unemployment rate, seasonally adjusted. Monthly labor market indicator.",
        "keywords": ["france", "french", "unemployment", "jobs", "labor"],
        "provider": "Eurostat",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "monthly",
    },
    "france_industrial_production": {
        "id": "OECD/MEI/FRA.PRINTO01.GYSA.M",
        "name": "France Industrial Production (YoY)",
        "description": "France industrial production growth, year-over-year.",
        "keywords": ["france", "french", "industrial production", "manufacturing", "output"],
        "provider": "OECD",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "monthly",
    },

    # === ITALY ===
    "italy_gdp": {
        "id": "IMF/WEO:2024-10/ITA.NGDP_RPCH.pcent_change",
        "name": "Italy GDP Growth (YoY)",
        "description": "Italy real GDP growth, year-over-year. Third largest eurozone economy.",
        "keywords": ["italy", "italian", "gdp", "europe"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "italy_inflation": {
        "id": "IMF/WEO:2024-10/ITA.PCPIPCH.pcent_change",
        "name": "Italy Inflation (CPI)",
        "description": "Italy consumer price inflation, year-over-year.",
        "keywords": ["italy", "italian", "inflation", "cpi", "europe"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "italy_unemployment": {
        "id": "Eurostat/une_rt_m/M.SA.TOTAL.PC_ACT.T.IT",
        "name": "Italy Unemployment Rate",
        "description": "Italy unemployment rate, seasonally adjusted. Historically higher than northern European peers.",
        "keywords": ["italy", "italian", "unemployment", "jobs", "labor"],
        "provider": "Eurostat",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "monthly",
    },
    "italy_industrial_production": {
        "id": "OECD/MEI/ITA.PRINTO01.GYSA.M",
        "name": "Italy Industrial Production (YoY)",
        "description": "Italy industrial production growth, year-over-year.",
        "keywords": ["italy", "italian", "industrial production", "manufacturing", "output"],
        "provider": "OECD",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "monthly",
    },

    # ==========================================================================
    # REGIONAL AGGREGATES - OECD, G7, Emerging Markets
    # ==========================================================================

    # === OECD TOTALS ===
    "oecd_gdp": {
        "id": "IMF/WEO:2024-10/OED.NGDP_RPCH.pcent_change",
        "name": "OECD GDP Growth (YoY)",
        "description": "OECD total real GDP growth, year-over-year. Aggregate growth for advanced economies.",
        "keywords": ["oecd", "advanced economies", "developed", "gdp", "global"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "oecd_inflation": {
        "id": "IMF/WEO:2024-10/OED.PCPIPCH.pcent_change",
        "name": "OECD Inflation (CPI)",
        "description": "OECD total consumer price inflation, year-over-year. Inflation trend across advanced economies.",
        "keywords": ["oecd", "advanced economies", "developed", "inflation", "global"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "oecd_unemployment": {
        "id": "IMF/WEO:2024-10/OED.LUR.pcent_total_labor_force",
        "name": "OECD Unemployment Rate",
        "description": "OECD total unemployment rate. Labor market conditions across advanced economies.",
        "keywords": ["oecd", "advanced economies", "developed", "unemployment", "global"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "level",
        "frequency": "annual",
    },

    # === EMERGING MARKETS ===
    "emerging_markets_gdp": {
        "id": "IMF/WEO:2024-10/EMD.NGDP_RPCH.pcent_change",
        "name": "Emerging Markets GDP Growth (YoY)",
        "description": "Emerging and developing economies real GDP growth, year-over-year. Growth in developing world.",
        "keywords": ["emerging markets", "developing", "em", "gdp", "global", "brics"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "emerging_markets_inflation": {
        "id": "IMF/WEO:2024-10/EMD.PCPIPCH.pcent_change",
        "name": "Emerging Markets Inflation (CPI)",
        "description": "Emerging and developing economies consumer price inflation. Inflation in developing world.",
        "keywords": ["emerging markets", "developing", "em", "inflation", "global", "brics"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },

    # === WORLD TOTALS ===
    "world_gdp": {
        "id": "IMF/WEO:2024-10/WEO.NGDP_RPCH.pcent_change",
        "name": "World GDP Growth (YoY)",
        "description": "World real GDP growth, year-over-year. Global economic output expansion.",
        "keywords": ["world", "global", "gdp", "international"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "world_inflation": {
        "id": "IMF/WEO:2024-10/WEO.PCPIPCH.pcent_change",
        "name": "World Inflation (CPI)",
        "description": "World consumer price inflation, year-over-year. Global inflation trends.",
        "keywords": ["world", "global", "inflation", "international"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },

    # ==========================================================================
    # ADDITIONAL EMERGING MARKETS
    # ==========================================================================

    # === INDONESIA ===
    "indonesia_gdp": {
        "id": "IMF/WEO:2024-10/IDN.NGDP_RPCH.pcent_change",
        "name": "Indonesia GDP Growth (YoY)",
        "description": "Indonesia real GDP growth, year-over-year. Southeast Asia's largest economy and G20 member.",
        "keywords": ["indonesia", "indonesian", "gdp", "asia", "asean", "g20"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "indonesia_inflation": {
        "id": "IMF/WEO:2024-10/IDN.PCPIPCH.pcent_change",
        "name": "Indonesia Inflation (CPI)",
        "description": "Indonesia consumer price inflation, year-over-year.",
        "keywords": ["indonesia", "indonesian", "inflation", "cpi", "asia"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },

    # === TURKEY ===
    "turkey_gdp": {
        "id": "IMF/WEO:2024-10/TUR.NGDP_RPCH.pcent_change",
        "name": "Turkey GDP Growth (YoY)",
        "description": "Turkey real GDP growth, year-over-year. Major emerging market at Europe-Asia crossroads.",
        "keywords": ["turkey", "turkish", "gdp", "emerging", "g20"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "turkey_inflation": {
        "id": "IMF/WEO:2024-10/TUR.PCPIPCH.pcent_change",
        "name": "Turkey Inflation (CPI)",
        "description": "Turkey consumer price inflation, year-over-year. Has experienced high inflation in recent years.",
        "keywords": ["turkey", "turkish", "inflation", "cpi"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "turkey_industrial_production": {
        "id": "OECD/MEI/TUR.PRINTO01.GYSA.M",
        "name": "Turkey Industrial Production (YoY)",
        "description": "Turkey industrial production growth, year-over-year.",
        "keywords": ["turkey", "turkish", "industrial production", "manufacturing"],
        "provider": "OECD",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "monthly",
    },

    # === SOUTH AFRICA ===
    "south_africa_gdp": {
        "id": "IMF/WEO:2024-10/ZAF.NGDP_RPCH.pcent_change",
        "name": "South Africa GDP Growth (YoY)",
        "description": "South Africa real GDP growth, year-over-year. Africa's most industrialized economy and BRICS member.",
        "keywords": ["south africa", "african", "gdp", "africa", "brics", "emerging"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "south_africa_inflation": {
        "id": "IMF/WEO:2024-10/ZAF.PCPIPCH.pcent_change",
        "name": "South Africa Inflation (CPI)",
        "description": "South Africa consumer price inflation, year-over-year.",
        "keywords": ["south africa", "african", "inflation", "cpi", "africa"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },

    # === RUSSIA ===
    "russia_gdp": {
        "id": "IMF/WEO:2024-10/RUS.NGDP_RPCH.pcent_change",
        "name": "Russia GDP Growth (YoY)",
        "description": "Russia real GDP growth, year-over-year. Major energy exporter and BRICS member.",
        "keywords": ["russia", "russian", "gdp", "brics", "energy"],
        "provider": "IMF",
        "measure_type": "real",
        "change_type": "yoy",
        "frequency": "annual",
    },
    "russia_inflation": {
        "id": "IMF/WEO:2024-10/RUS.PCPIPCH.pcent_change",
        "name": "Russia Inflation (CPI)",
        "description": "Russia consumer price inflation, year-over-year.",
        "keywords": ["russia", "russian", "inflation", "cpi"],
        "provider": "IMF",
        "measure_type": "rate",
        "change_type": "yoy",
        "frequency": "annual",
    },
}

# Query plans for international queries
INTERNATIONAL_QUERY_PLANS = {
    # ==========================================================================
    # Comparison queries - US vs international
    # ==========================================================================
    "us compared to eurozone": {
        "series": ["eurozone_gdp"],  # Will be combined with US GDP from FRED
        "explanation": "Eurozone GDP growth for comparison with US.",
        "compare_with_us": True,
    },
    "us vs eurozone": {
        "series": ["eurozone_gdp"],
        "explanation": "Eurozone GDP growth for comparison with US.",
        "compare_with_us": True,
    },
    "growth in the us compared to eurozone": {
        "series": ["eurozone_gdp"],
        "explanation": "Eurozone GDP growth for comparison with US.",
        "compare_with_us": True,
    },

    # ==========================================================================
    # EUROZONE
    # ==========================================================================
    "eurozone economy": {
        "series": ["eurozone_gdp", "eurozone_inflation", "eurozone_unemployment"],
        "explanation": "Key Eurozone economic indicators: GDP, inflation, and unemployment.",
    },
    "how is europe doing": {
        "series": ["eurozone_gdp", "eurozone_inflation", "germany_gdp"],
        "explanation": "European economic indicators.",
    },
    "europe economy": {
        "series": ["eurozone_gdp", "eurozone_inflation", "germany_gdp"],
        "explanation": "European economic indicators.",
    },
    "eurozone gdp": {
        "series": ["eurozone_gdp"],
        "explanation": "Eurozone quarterly GDP growth.",
    },
    "ecb rate": {
        "series": ["ecb_rate"],
        "explanation": "ECB main refinancing rate.",
    },
    "eurozone inflation": {
        "series": ["eurozone_inflation"],
        "explanation": "Eurozone HICP inflation.",
    },
    "eurozone unemployment": {
        "series": ["eurozone_unemployment"],
        "explanation": "Eurozone unemployment rate.",
    },
    "eurozone industrial production": {
        "series": ["eurozone_industrial_production"],
        "explanation": "Eurozone industrial production index.",
    },
    "eurozone trade": {
        "series": ["eurozone_current_account"],
        "explanation": "Eurozone current account balance.",
    },

    # ==========================================================================
    # UK
    # ==========================================================================
    "uk economy": {
        "series": ["uk_gdp", "uk_inflation", "uk_unemployment"],
        "explanation": "UK economic indicators: GDP, inflation, and unemployment.",
    },
    "how is the uk doing": {
        "series": ["uk_gdp", "uk_inflation", "uk_unemployment"],
        "explanation": "UK economic indicators from IMF.",
    },
    "uk gdp": {
        "series": ["uk_gdp"],
        "explanation": "UK real GDP growth.",
    },
    "uk inflation": {
        "series": ["uk_inflation"],
        "explanation": "UK consumer price inflation.",
    },
    "uk unemployment": {
        "series": ["uk_unemployment"],
        "explanation": "UK unemployment rate.",
    },
    "uk trade": {
        "series": ["uk_current_account"],
        "explanation": "UK current account balance.",
    },
    "britain economy": {
        "series": ["uk_gdp", "uk_inflation", "uk_unemployment"],
        "explanation": "UK economic indicators.",
    },

    # ==========================================================================
    # JAPAN
    # ==========================================================================
    "japan economy": {
        "series": ["japan_gdp", "japan_inflation", "japan_unemployment"],
        "explanation": "Japan economic indicators: GDP, inflation, and unemployment.",
    },
    "how is japan doing": {
        "series": ["japan_gdp", "japan_inflation", "japan_unemployment"],
        "explanation": "Japan economic indicators from IMF.",
    },
    "japan gdp": {
        "series": ["japan_gdp"],
        "explanation": "Japan real GDP growth.",
    },
    "japan inflation": {
        "series": ["japan_inflation"],
        "explanation": "Japan consumer price inflation.",
    },
    "japan unemployment": {
        "series": ["japan_unemployment"],
        "explanation": "Japan unemployment rate.",
    },
    "japan industrial production": {
        "series": ["japan_industrial_production"],
        "explanation": "Japan industrial production growth.",
    },
    "japan trade": {
        "series": ["japan_current_account"],
        "explanation": "Japan current account balance.",
    },

    # ==========================================================================
    # CHINA
    # ==========================================================================
    "china economy": {
        "series": ["china_gdp", "china_inflation", "china_unemployment"],
        "explanation": "China economic indicators: GDP, inflation, and unemployment.",
    },
    "how is china doing": {
        "series": ["china_gdp", "china_inflation", "china_unemployment"],
        "explanation": "China economic indicators from IMF.",
    },
    "china gdp": {
        "series": ["china_gdp"],
        "explanation": "China real GDP growth.",
    },
    "china inflation": {
        "series": ["china_inflation"],
        "explanation": "China consumer price inflation.",
    },
    "china unemployment": {
        "series": ["china_unemployment"],
        "explanation": "China unemployment rate.",
    },
    "china trade": {
        "series": ["china_current_account"],
        "explanation": "China current account balance.",
    },

    # ==========================================================================
    # GERMANY
    # ==========================================================================
    "germany economy": {
        "series": ["germany_gdp", "germany_inflation", "germany_unemployment"],
        "explanation": "Germany economic indicators: GDP, inflation, and unemployment.",
    },
    "how is germany doing": {
        "series": ["germany_gdp", "germany_inflation", "germany_unemployment"],
        "explanation": "Germany economic indicators.",
    },
    "germany gdp": {
        "series": ["germany_gdp"],
        "explanation": "Germany real GDP growth.",
    },
    "germany inflation": {
        "series": ["germany_inflation"],
        "explanation": "Germany consumer price inflation.",
    },
    "germany unemployment": {
        "series": ["germany_unemployment"],
        "explanation": "Germany unemployment rate.",
    },
    "germany industrial production": {
        "series": ["germany_industrial_production"],
        "explanation": "Germany industrial production growth.",
    },
    "germany trade": {
        "series": ["germany_current_account"],
        "explanation": "Germany current account balance.",
    },

    # ==========================================================================
    # FRANCE
    # ==========================================================================
    "france economy": {
        "series": ["france_gdp", "france_inflation", "france_unemployment"],
        "explanation": "France economic indicators: GDP, inflation, and unemployment.",
    },
    "how is france doing": {
        "series": ["france_gdp", "france_inflation", "france_unemployment"],
        "explanation": "France economic indicators.",
    },
    "france gdp": {
        "series": ["france_gdp"],
        "explanation": "France real GDP growth.",
    },
    "france inflation": {
        "series": ["france_inflation"],
        "explanation": "France consumer price inflation.",
    },
    "france unemployment": {
        "series": ["france_unemployment"],
        "explanation": "France unemployment rate.",
    },
    "france industrial production": {
        "series": ["france_industrial_production"],
        "explanation": "France industrial production growth.",
    },

    # ==========================================================================
    # ITALY
    # ==========================================================================
    "italy economy": {
        "series": ["italy_gdp", "italy_inflation", "italy_unemployment"],
        "explanation": "Italy economic indicators: GDP, inflation, and unemployment.",
    },
    "how is italy doing": {
        "series": ["italy_gdp", "italy_inflation", "italy_unemployment"],
        "explanation": "Italy economic indicators.",
    },
    "italy gdp": {
        "series": ["italy_gdp"],
        "explanation": "Italy real GDP growth.",
    },
    "italy inflation": {
        "series": ["italy_inflation"],
        "explanation": "Italy consumer price inflation.",
    },
    "italy unemployment": {
        "series": ["italy_unemployment"],
        "explanation": "Italy unemployment rate.",
    },
    "italy industrial production": {
        "series": ["italy_industrial_production"],
        "explanation": "Italy industrial production growth.",
    },

    # ==========================================================================
    # SOUTH KOREA
    # ==========================================================================
    "south korea economy": {
        "series": ["south_korea_gdp", "south_korea_inflation", "south_korea_unemployment"],
        "explanation": "South Korea economic indicators: GDP, inflation, and unemployment.",
    },
    "korea economy": {
        "series": ["south_korea_gdp", "south_korea_inflation", "south_korea_unemployment"],
        "explanation": "South Korea economic indicators.",
    },
    "how is south korea doing": {
        "series": ["south_korea_gdp", "south_korea_inflation", "south_korea_unemployment"],
        "explanation": "South Korea economic indicators.",
    },
    "how is korea doing": {
        "series": ["south_korea_gdp", "south_korea_inflation", "south_korea_unemployment"],
        "explanation": "South Korea economic indicators.",
    },
    "south korea gdp": {
        "series": ["south_korea_gdp"],
        "explanation": "South Korea real GDP growth.",
    },
    "korea gdp": {
        "series": ["south_korea_gdp"],
        "explanation": "South Korea real GDP growth.",
    },
    "south korea inflation": {
        "series": ["south_korea_inflation"],
        "explanation": "South Korea consumer price inflation.",
    },
    "south korea unemployment": {
        "series": ["south_korea_unemployment"],
        "explanation": "South Korea unemployment rate.",
    },
    "south korea industrial production": {
        "series": ["south_korea_industrial_production"],
        "explanation": "South Korea industrial production growth.",
    },
    "south korea trade": {
        "series": ["south_korea_current_account"],
        "explanation": "South Korea current account balance.",
    },

    # ==========================================================================
    # AUSTRALIA
    # ==========================================================================
    "australia economy": {
        "series": ["australia_gdp", "australia_inflation", "australia_unemployment"],
        "explanation": "Australia economic indicators: GDP, inflation, and unemployment.",
    },
    "how is australia doing": {
        "series": ["australia_gdp", "australia_inflation", "australia_unemployment"],
        "explanation": "Australia economic indicators.",
    },
    "australia gdp": {
        "series": ["australia_gdp"],
        "explanation": "Australia real GDP growth.",
    },
    "australia inflation": {
        "series": ["australia_inflation"],
        "explanation": "Australia consumer price inflation.",
    },
    "australia unemployment": {
        "series": ["australia_unemployment"],
        "explanation": "Australia unemployment rate.",
    },
    "australia trade": {
        "series": ["australia_current_account"],
        "explanation": "Australia current account balance.",
    },
    "rba": {
        "series": ["australia_gdp", "australia_inflation"],
        "explanation": "Key indicators for Reserve Bank of Australia monetary policy.",
    },

    # ==========================================================================
    # CANADA
    # ==========================================================================
    "canada economy": {
        "series": ["canada_gdp", "canada_inflation", "canada_unemployment"],
        "explanation": "Canada economic indicators: GDP, inflation, and unemployment.",
    },
    "how is canada doing": {
        "series": ["canada_gdp", "canada_inflation", "canada_unemployment"],
        "explanation": "Canada economic indicators.",
    },
    "canada gdp": {
        "series": ["canada_gdp"],
        "explanation": "Canada real GDP growth.",
    },
    "canada inflation": {
        "series": ["canada_inflation"],
        "explanation": "Canada consumer price inflation.",
    },
    "canada unemployment": {
        "series": ["canada_unemployment"],
        "explanation": "Canada unemployment rate.",
    },
    "canada industrial production": {
        "series": ["canada_industrial_production"],
        "explanation": "Canada industrial production growth.",
    },
    "canada trade": {
        "series": ["canada_current_account"],
        "explanation": "Canada current account balance.",
    },
    "bank of canada": {
        "series": ["canada_gdp", "canada_inflation"],
        "explanation": "Key indicators for Bank of Canada monetary policy.",
    },

    # ==========================================================================
    # MEXICO
    # ==========================================================================
    "mexico economy": {
        "series": ["mexico_gdp", "mexico_inflation", "mexico_unemployment"],
        "explanation": "Mexico economic indicators: GDP, inflation, and unemployment.",
    },
    "how is mexico doing": {
        "series": ["mexico_gdp", "mexico_inflation", "mexico_unemployment"],
        "explanation": "Mexico economic indicators.",
    },
    "mexico gdp": {
        "series": ["mexico_gdp"],
        "explanation": "Mexico real GDP growth.",
    },
    "mexico inflation": {
        "series": ["mexico_inflation"],
        "explanation": "Mexico consumer price inflation.",
    },
    "mexico unemployment": {
        "series": ["mexico_unemployment"],
        "explanation": "Mexico unemployment rate.",
    },
    "mexico trade": {
        "series": ["mexico_current_account"],
        "explanation": "Mexico current account balance.",
    },
    "banxico": {
        "series": ["mexico_gdp", "mexico_inflation"],
        "explanation": "Key indicators for Banxico (Bank of Mexico) monetary policy.",
    },

    # ==========================================================================
    # INDIA
    # ==========================================================================
    "india economy": {
        "series": ["india_gdp", "india_inflation", "india_unemployment"],
        "explanation": "India economic indicators: GDP, inflation, and unemployment.",
    },
    "how is india doing": {
        "series": ["india_gdp", "india_inflation", "india_unemployment"],
        "explanation": "India economic indicators.",
    },
    "india gdp": {
        "series": ["india_gdp"],
        "explanation": "India real GDP growth.",
    },
    "india inflation": {
        "series": ["india_inflation"],
        "explanation": "India consumer price inflation.",
    },
    "india unemployment": {
        "series": ["india_unemployment"],
        "explanation": "India unemployment rate.",
    },
    "india trade": {
        "series": ["india_current_account"],
        "explanation": "India current account balance.",
    },
    "rbi": {
        "series": ["india_gdp", "india_inflation"],
        "explanation": "Key indicators for Reserve Bank of India monetary policy.",
    },

    # ==========================================================================
    # BRAZIL
    # ==========================================================================
    "brazil economy": {
        "series": ["brazil_gdp", "brazil_inflation", "brazil_unemployment"],
        "explanation": "Brazil economic indicators: GDP, inflation, and unemployment.",
    },
    "how is brazil doing": {
        "series": ["brazil_gdp", "brazil_inflation", "brazil_unemployment"],
        "explanation": "Brazil economic indicators.",
    },
    "brazil gdp": {
        "series": ["brazil_gdp"],
        "explanation": "Brazil real GDP growth.",
    },
    "brazil inflation": {
        "series": ["brazil_inflation"],
        "explanation": "Brazil consumer price inflation.",
    },
    "brazil unemployment": {
        "series": ["brazil_unemployment"],
        "explanation": "Brazil unemployment rate.",
    },
    "brazil industrial production": {
        "series": ["brazil_industrial_production"],
        "explanation": "Brazil industrial production growth.",
    },
    "brazil trade": {
        "series": ["brazil_current_account"],
        "explanation": "Brazil current account balance.",
    },
    "bcb": {
        "series": ["brazil_gdp", "brazil_inflation"],
        "explanation": "Key indicators for Central Bank of Brazil monetary policy.",
    },

    # ==========================================================================
    # INDONESIA
    # ==========================================================================
    "indonesia economy": {
        "series": ["indonesia_gdp", "indonesia_inflation"],
        "explanation": "Indonesia economic indicators: GDP and inflation.",
    },
    "how is indonesia doing": {
        "series": ["indonesia_gdp", "indonesia_inflation"],
        "explanation": "Indonesia economic indicators.",
    },
    "indonesia gdp": {
        "series": ["indonesia_gdp"],
        "explanation": "Indonesia real GDP growth.",
    },
    "indonesia inflation": {
        "series": ["indonesia_inflation"],
        "explanation": "Indonesia consumer price inflation.",
    },

    # ==========================================================================
    # TURKEY
    # ==========================================================================
    "turkey economy": {
        "series": ["turkey_gdp", "turkey_inflation"],
        "explanation": "Turkey economic indicators: GDP and inflation.",
    },
    "how is turkey doing": {
        "series": ["turkey_gdp", "turkey_inflation"],
        "explanation": "Turkey economic indicators.",
    },
    "turkey gdp": {
        "series": ["turkey_gdp"],
        "explanation": "Turkey real GDP growth.",
    },
    "turkey inflation": {
        "series": ["turkey_inflation"],
        "explanation": "Turkey consumer price inflation.",
    },
    "turkey industrial production": {
        "series": ["turkey_industrial_production"],
        "explanation": "Turkey industrial production growth.",
    },

    # ==========================================================================
    # SOUTH AFRICA
    # ==========================================================================
    "south africa economy": {
        "series": ["south_africa_gdp", "south_africa_inflation"],
        "explanation": "South Africa economic indicators: GDP and inflation.",
    },
    "how is south africa doing": {
        "series": ["south_africa_gdp", "south_africa_inflation"],
        "explanation": "South Africa economic indicators.",
    },
    "south africa gdp": {
        "series": ["south_africa_gdp"],
        "explanation": "South Africa real GDP growth.",
    },
    "south africa inflation": {
        "series": ["south_africa_inflation"],
        "explanation": "South Africa consumer price inflation.",
    },

    # ==========================================================================
    # RUSSIA
    # ==========================================================================
    "russia economy": {
        "series": ["russia_gdp", "russia_inflation"],
        "explanation": "Russia economic indicators: GDP and inflation.",
    },
    "how is russia doing": {
        "series": ["russia_gdp", "russia_inflation"],
        "explanation": "Russia economic indicators.",
    },
    "russia gdp": {
        "series": ["russia_gdp"],
        "explanation": "Russia real GDP growth.",
    },
    "russia inflation": {
        "series": ["russia_inflation"],
        "explanation": "Russia consumer price inflation.",
    },

    # ==========================================================================
    # REGIONAL AGGREGATES
    # ==========================================================================
    "global economy": {
        "series": ["world_gdp", "world_inflation"],
        "explanation": "World GDP and inflation trends.",
    },
    "world economy": {
        "series": ["world_gdp", "world_inflation"],
        "explanation": "World GDP and inflation trends.",
    },
    "global gdp": {
        "series": ["world_gdp"],
        "explanation": "World real GDP growth.",
    },
    "world gdp": {
        "series": ["world_gdp"],
        "explanation": "World real GDP growth.",
    },
    "global inflation": {
        "series": ["world_inflation"],
        "explanation": "World consumer price inflation.",
    },
    "world inflation": {
        "series": ["world_inflation"],
        "explanation": "World consumer price inflation.",
    },
    "oecd economy": {
        "series": ["oecd_gdp", "oecd_inflation", "oecd_unemployment"],
        "explanation": "OECD total economic indicators for advanced economies.",
    },
    "advanced economies": {
        "series": ["oecd_gdp", "oecd_inflation", "oecd_unemployment"],
        "explanation": "OECD advanced economies aggregate indicators.",
    },
    "oecd gdp": {
        "series": ["oecd_gdp"],
        "explanation": "OECD total real GDP growth.",
    },
    "oecd inflation": {
        "series": ["oecd_inflation"],
        "explanation": "OECD total consumer price inflation.",
    },
    "oecd unemployment": {
        "series": ["oecd_unemployment"],
        "explanation": "OECD total unemployment rate.",
    },
    "emerging markets": {
        "series": ["emerging_markets_gdp", "emerging_markets_inflation"],
        "explanation": "Emerging and developing economies GDP and inflation.",
    },
    "emerging markets gdp": {
        "series": ["emerging_markets_gdp"],
        "explanation": "Emerging markets real GDP growth.",
    },
    "emerging markets inflation": {
        "series": ["emerging_markets_inflation"],
        "explanation": "Emerging markets consumer price inflation.",
    },
    "brics": {
        "series": ["brazil_gdp", "russia_gdp", "india_gdp", "china_gdp", "south_africa_gdp"],
        "explanation": "BRICS nations (Brazil, Russia, India, China, South Africa) GDP growth.",
    },
    "brics economies": {
        "series": ["brazil_gdp", "russia_gdp", "india_gdp", "china_gdp", "south_africa_gdp"],
        "explanation": "BRICS nations economic growth.",
    },
    "g7 gdp": {
        "series": ["uk_gdp", "germany_gdp", "france_gdp", "italy_gdp", "japan_gdp", "canada_gdp"],
        "explanation": "G7 nations GDP growth (excluding US which is from FRED).",
    },
    "g7 economy": {
        "series": ["uk_gdp", "germany_gdp", "france_gdp", "italy_gdp", "japan_gdp", "canada_gdp"],
        "explanation": "G7 nations economic growth (excluding US).",
    },
    "asean economy": {
        "series": ["indonesia_gdp"],
        "explanation": "Major ASEAN economy indicator (Indonesia).",
    },
    "asia pacific economy": {
        "series": ["china_gdp", "japan_gdp", "south_korea_gdp", "australia_gdp", "india_gdp"],
        "explanation": "Major Asia-Pacific economies GDP growth.",
    },
    "latin america economy": {
        "series": ["brazil_gdp", "mexico_gdp"],
        "explanation": "Major Latin American economies GDP growth.",
    },

    # ==========================================================================
    # CROSS-CUTTING THEMES
    # ==========================================================================
    "global industrial production": {
        "series": ["germany_industrial_production", "japan_industrial_production", "south_korea_industrial_production"],
        "explanation": "Industrial production trends in major manufacturing economies.",
    },
    "global unemployment": {
        "series": ["eurozone_unemployment", "uk_unemployment", "japan_unemployment", "canada_unemployment"],
        "explanation": "Unemployment rates across major developed economies.",
    },
    "global current account": {
        "series": ["china_current_account", "germany_current_account", "japan_current_account"],
        "explanation": "Current account balances for major surplus economies.",
    },
    "global trade imbalances": {
        "series": ["china_current_account", "germany_current_account", "japan_current_account"],
        "explanation": "Current account balances showing global trade imbalances.",
    },
}


def _get_cached(key: str) -> Optional[dict]:
    """Get cached result if still valid."""
    if key in _cache:
        data, timestamp = _cache[key]
        if datetime.now() - timestamp < _cache_ttl:
            return data
    return None


def _set_cache(key: str, data: dict) -> None:
    """Cache result with timestamp."""
    _cache[key] = (data, datetime.now())


def fetch_series(series_key: str) -> Optional[dict]:
    """
    Fetch a series from DBnomics.

    Args:
        series_key: Key from INTERNATIONAL_SERIES (e.g., "eurozone_gdp")

    Returns:
        Dict with dates, values, and metadata, or None on error.
    """
    if series_key not in INTERNATIONAL_SERIES:
        return None

    cache_key = f"dbnomics_{series_key}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    series_info = INTERNATIONAL_SERIES[series_key]
    series_id = series_info["id"]

    try:
        url = f"{DBNOMICS_API}/series/{series_id}?observations=1"
        req = Request(url, headers={"Accept": "application/json"})
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())

        docs = data.get("series", {}).get("docs", [])
        if not docs:
            return None

        series_data = docs[0]
        periods = series_data.get("period", [])
        values = series_data.get("value", [])

        # Filter out None values
        clean_periods = []
        clean_values = []
        for p, v in zip(periods, values):
            if v is not None:
                clean_periods.append(p)
                clean_values.append(v)

        result = {
            "id": series_key,
            "dbnomics_id": series_id,
            "name": series_info["name"],
            "description": series_info["description"],
            "provider": series_info["provider"],
            "dates": clean_periods,
            "values": clean_values,
            "frequency": series_data.get("@frequency", "unknown"),
            "unit": series_data.get("unit", ""),
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[DBnomics] Error fetching {series_key}: {e}")
        return None


def get_observations_dbnomics(series_key: str) -> tuple:
    """
    Get observations in FRED-compatible format.

    Returns:
        Tuple of (dates, values, info) for compatibility with app.py
    """
    data = fetch_series(series_key)
    if not data:
        return None, None, None

    # Convert periods to FRED-style dates (YYYY-MM-DD)
    dates = []
    for p in data["dates"]:
        if "Q" in p:
            # Quarterly: 2024-Q1 -> 2024-03-31
            year, q = p.split("-Q")
            month = {"1": "03", "2": "06", "3": "09", "4": "12"}[q]
            dates.append(f"{year}-{month}-01")
        elif len(p) == 4:
            # Annual: 2024 -> 2024-12-31
            dates.append(f"{p}-12-31")
        elif len(p) == 7:
            # Monthly: 2024-01 -> 2024-01-01
            dates.append(f"{p}-01")
        else:
            dates.append(p)

    info = {
        "id": data["dbnomics_id"],
        "name": data["name"],
        "title": data["name"],
        "units": data.get("unit", ""),
        "frequency": data["frequency"],
        "source": f"DBnomics ({data['provider']})",
    }

    return dates, data["values"], info


def find_international_plan(query: str) -> Optional[dict]:
    """
    Find a query plan for international data.

    Returns dict with 'series' and 'explanation' if found.
    """
    query_lower = query.lower().strip()

    # Exact/partial match on plans first (check all plans, find best match)
    best_plan = None
    best_match_len = 0
    for plan_query, plan in INTERNATIONAL_QUERY_PLANS.items():
        if plan_query in query_lower:
            if len(plan_query) > best_match_len:
                best_match_len = len(plan_query)
                best_plan = plan
        elif query_lower in plan_query:
            if len(query_lower) > best_match_len:
                best_match_len = len(query_lower)
                best_plan = plan

    if best_plan:
        return {**best_plan, "source": "dbnomics"}

    # Score-based keyword matching on series
    # Boost GDP series if "growth" is in query
    is_growth_query = "growth" in query_lower or "gdp" in query_lower
    is_inflation_query = "inflation" in query_lower or "cpi" in query_lower or "prices" in query_lower

    matches = []
    for series_key, meta in INTERNATIONAL_SERIES.items():
        keywords = meta.get("keywords", [])
        score = 0
        for kw in keywords:
            if kw in query_lower:
                # Longer keyword matches score higher
                score += len(kw)

        # Apply category boost based on query intent
        if score > 0:
            if is_growth_query and "gdp" in series_key:
                score += 10
            elif is_inflation_query and "inflation" in series_key:
                score += 10

            matches.append((series_key, meta, score))

    # Return highest scoring match
    if matches:
        matches.sort(key=lambda x: -x[2])
        best_key, best_meta, _ = matches[0]
        return {
            "series": [best_key],
            "explanation": best_meta.get("description"),
            "source": "dbnomics",
        }

    return None


def is_international_query(query: str) -> bool:
    """
    Check if query asks about international/non-US data.

    Returns True if the query contains keywords for:
    - Specific countries (UK, Japan, China, Germany, France, Italy, etc.)
    - Regional aggregates (Eurozone, OECD, G7, BRICS, emerging markets)
    - Central banks (ECB, BOE, BOJ, RBA, BOC, Banxico, RBI, BCB)
    - Global/world economy queries
    """
    query_lower = query.lower()
    intl_keywords = [
        # Regional aggregates
        "eurozone", "euro area", "europe", "european", "eu",
        "oecd", "g7", "g20", "brics",
        "global", "world",
        "emerging market", "emerging economies", "advanced economies",
        "asia pacific", "latin america", "asean",

        # UK
        "uk", "britain", "british", "england", "united kingdom",

        # Japan
        "japan", "japanese",

        # China
        "china", "chinese",

        # Germany
        "germany", "german",

        # France
        "france", "french",

        # Italy
        "italy", "italian",

        # South Korea
        "south korea", "korea", "korean",

        # Australia
        "australia", "australian",

        # Canada
        "canada", "canadian",

        # Mexico
        "mexico", "mexican",

        # India
        "india", "indian",

        # Brazil
        "brazil", "brazilian",

        # Indonesia
        "indonesia", "indonesian",

        # Turkey
        "turkey", "turkish",

        # South Africa
        "south africa", "african",

        # Russia
        "russia", "russian",

        # Central banks
        "ecb", "boe", "boj", "rba", "boc", "banxico", "rbi", "bcb",
        "bank of england", "bank of japan", "bank of canada",
        "reserve bank of australia", "reserve bank of india",
    ]
    return any(kw in query_lower for kw in intl_keywords)


# Quick test
if __name__ == "__main__":
    print("Testing DBnomics integration...\n")
    print(f"Total series in catalog: {len(INTERNATIONAL_SERIES)}")
    print(f"Total query plans: {len(INTERNATIONAL_QUERY_PLANS)}")
    print()

    # Test a representative sample of series from different providers/countries
    test_series = [
        "eurozone_gdp",        # Eurostat
        "south_korea_gdp",     # IMF WEO - new country
        "brazil_unemployment", # OECD MEI - new indicator
        "germany_industrial_production",  # OECD MEI - industrial production
        "world_gdp",           # IMF WEO - global aggregate
    ]

    print("Fetching sample series:")
    print("-" * 50)
    for key in test_series:
        print(f"Fetching {key}...")
        dates, values, info = get_observations_dbnomics(key)
        if dates:
            print(f"  {info['name']}")
            print(f"  Source: {info['source']}")
            print(f"  Latest: {dates[-1]} = {values[-1]}")
            print()
        else:
            print(f"  Failed to fetch\n")

    print("=" * 50)
    print("\nQuery matching tests:\n")

    test_queries = [
        "how is the eurozone doing?",
        "china gdp growth",
        "uk economy",
        "global economic outlook",
        "south korea economy",
        "brazil industrial production",
        "emerging markets gdp",
        "brics economies",
        "australia unemployment",
        "g7 gdp",
    ]

    for q in test_queries:
        plan = find_international_plan(q)
        if plan:
            print(f"Query: '{q}'")
            print(f"  Series: {plan['series']}")
        else:
            print(f"Query: '{q}' - No plan found")
        print()

    # Summary of coverage
    print("=" * 50)
    print("\nSeries coverage by country/region:")
    print("-" * 50)
    countries = {}
    for key in INTERNATIONAL_SERIES:
        # Extract country/region from key
        parts = key.split("_")
        if len(parts) >= 2:
            country = parts[0]
            if parts[0] == "south" and parts[1] in ["korea", "africa"]:
                country = f"{parts[0]}_{parts[1]}"
            elif parts[0] == "emerging":
                country = "emerging_markets"
            countries[country] = countries.get(country, 0) + 1
    for country, count in sorted(countries.items(), key=lambda x: -x[1]):
        print(f"  {country}: {count} series")
