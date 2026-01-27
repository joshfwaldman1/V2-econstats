"""
EIA (Energy Information Administration) data integration for EconStats.

Provides access to energy data including:
- Crude oil prices (WTI, Brent)
- Gasoline prices (retail, wholesale)
- Natural gas prices (Henry Hub)
- Electricity prices
- Petroleum inventories

API Documentation: https://www.eia.gov/opendata/documentation.php
Registration (free): https://www.eia.gov/opendata/register.php
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

# API Key from environment
EIA_API_KEY = os.environ.get("EIA_API_KEY", "")

# Base URL for EIA API v2
EIA_BASE_URL = "https://api.eia.gov/v2"

# =============================================================================
# EIA SERIES CATALOG
# =============================================================================

EIA_SERIES = {
    # Crude Oil Prices
    'eia_wti_crude': {
        'name': 'WTI Crude Oil Spot Price',
        'description': 'West Texas Intermediate crude oil spot price, Cushing OK ($/barrel)',
        'series_id': 'PET.RWTC.W',  # Weekly
        'route': '/petroleum/pri/spt/data',
        'facets': {'series': 'RWTC'},
        'units': 'dollars per barrel',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['oil', 'crude', 'wti', 'petroleum', 'energy'],
        'fred_equivalent': 'DCOILWTICO',  # FRED has this too
    },
    'eia_brent_crude': {
        'name': 'Brent Crude Oil Spot Price',
        'description': 'Brent crude oil spot price, Europe ($/barrel)',
        'series_id': 'PET.RBRTE.W',
        'route': '/petroleum/pri/spt/data',
        'facets': {'series': 'RBRTE'},
        'units': 'dollars per barrel',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['oil', 'crude', 'brent', 'petroleum', 'energy', 'europe'],
        'fred_equivalent': 'DCOILBRENTEU',
    },

    # Gasoline Prices
    'eia_gasoline_retail': {
        'name': 'US Regular Gasoline Retail Price',
        'description': 'Average retail price of regular grade gasoline, all formulations ($/gallon)',
        'series_id': 'PET.EMM_EPMR_PTE_NUS_DPG.W',
        'route': '/petroleum/pri/gnd/data',
        'facets': {'series': 'EMM_EPMR_PTE_NUS_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gas', 'gasoline', 'fuel', 'retail', 'pump price'],
        'fred_equivalent': 'GASREGW',
    },
    'eia_diesel_retail': {
        'name': 'US Diesel Retail Price',
        'description': 'Average retail price of diesel fuel ($/gallon)',
        'series_id': 'PET.EMD_EPD2D_PTE_NUS_DPG.W',
        'route': '/petroleum/pri/gnd/data',
        'facets': {'series': 'EMD_EPD2D_PTE_NUS_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['diesel', 'fuel', 'trucking', 'shipping'],
    },

    # Natural Gas
    'eia_natural_gas_henry_hub': {
        'name': 'Henry Hub Natural Gas Spot Price',
        'description': 'Natural gas spot price at Henry Hub, Louisiana ($/MMBtu)',
        'series_id': 'NG.RNGWHHD.M',  # Monthly
        'route': '/natural-gas/pri/sum/data',
        'facets': {'series': 'RNGWHHD'},
        'units': 'dollars per MMBtu',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['natural gas', 'gas', 'henry hub', 'energy', 'lng'],
        'fred_equivalent': 'MHHNGSP',
    },

    # Petroleum Inventories
    'eia_crude_stocks': {
        'name': 'US Crude Oil Stocks',
        'description': 'Total US crude oil stocks excluding SPR (million barrels)',
        'series_id': 'PET.WCESTUS1.W',
        'route': '/petroleum/stoc/wstk/data',
        'facets': {'series': 'WCESTUS1'},
        'units': 'million barrels',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['crude', 'oil', 'inventory', 'stocks', 'supply'],
    },
    'eia_gasoline_stocks': {
        'name': 'US Gasoline Stocks',
        'description': 'Total US motor gasoline stocks (million barrels)',
        'series_id': 'PET.WGTSTUS1.W',
        'route': '/petroleum/stoc/wstk/data',
        'facets': {'series': 'WGTSTUS1'},
        'units': 'million barrels',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gasoline', 'inventory', 'stocks', 'supply'],
    },

    # Electricity (average retail price)
    'eia_electricity_residential': {
        'name': 'US Residential Electricity Price',
        'description': 'Average retail price of electricity for residential customers (cents/kWh)',
        'series_id': 'ELEC.PRICE.US-RES.M',
        'route': '/electricity/retail-sales/data',
        'facets': {'sectorid': 'RES', 'stateid': 'US'},
        'units': 'cents per kWh',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'power', 'residential', 'utility', 'electric bill'],
    },

    # Production
    'eia_crude_production': {
        'name': 'US Crude Oil Production',
        'description': 'US field production of crude oil (thousand barrels per day)',
        'series_id': 'PET.WCRFPUS2.W',
        'route': '/petroleum/sum/sndw/data',
        'facets': {'series': 'WCRFPUS2'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['crude', 'oil', 'production', 'supply', 'output'],
    },

    # ==========================================================================
    # CRUDE OIL IMPORTS/EXPORTS
    # ==========================================================================
    'eia_crude_imports': {
        'name': 'US Crude Oil Imports',
        'description': 'Weekly US imports of crude oil, tracking foreign oil dependency and trade flows (thousand barrels per day)',
        'series_id': 'PET.WCRIMUS2.W',
        'route': '/petroleum/move/wkly/data',
        'facets': {'series': 'WCRIMUS2'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['crude', 'oil', 'imports', 'trade', 'foreign', 'dependency'],
    },
    'eia_crude_exports': {
        'name': 'US Crude Oil Exports',
        'description': 'Weekly US exports of crude oil, reflecting US energy independence and global supply role (thousand barrels per day)',
        'series_id': 'PET.WCREXUS2.W',
        'route': '/petroleum/move/wkly/data',
        'facets': {'series': 'WCREXUS2'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['crude', 'oil', 'exports', 'trade', 'energy independence'],
    },
    'eia_crude_net_imports': {
        'name': 'US Crude Oil Net Imports',
        'description': 'Weekly US net imports of crude oil (imports minus exports), key measure of energy trade balance (thousand barrels per day)',
        'series_id': 'PET.WCRNTUS2.W',
        'route': '/petroleum/move/wkly/data',
        'facets': {'series': 'WCRNTUS2'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['crude', 'oil', 'net imports', 'trade balance', 'energy'],
    },

    # ==========================================================================
    # REFINERY OPERATIONS
    # ==========================================================================
    'eia_refinery_utilization': {
        'name': 'US Refinery Utilization Rate',
        'description': 'Percent utilization of US refinery operable capacity, indicates refining sector health and fuel supply capacity',
        'series_id': 'PET.WPULEUS3.W',
        'route': '/petroleum/pnp/wiup/data',
        'facets': {'series': 'WPULEUS3'},
        'units': 'percent',
        'frequency': 'weekly',
        'measure_type': 'rate',
        'change_type': 'level',
        'keywords': ['refinery', 'utilization', 'capacity', 'gasoline', 'diesel', 'supply'],
    },
    'eia_refinery_inputs': {
        'name': 'US Refinery Crude Oil Inputs',
        'description': 'Weekly gross inputs to US crude oil distillation units, measures refinery processing activity (thousand barrels per day)',
        'series_id': 'PET.WGIRIUS2.W',
        'route': '/petroleum/pnp/wiup/data',
        'facets': {'series': 'WGIRIUS2'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['refinery', 'inputs', 'crude', 'processing', 'distillation'],
    },

    # ==========================================================================
    # REGIONAL CRUDE OIL STOCKS (PADD REGIONS)
    # ==========================================================================
    'eia_crude_stocks_gulf_coast': {
        'name': 'Gulf Coast (PADD 3) Crude Oil Stocks',
        'description': 'Crude oil stocks in Gulf Coast region (PADD 3) including Texas and Louisiana refineries (million barrels)',
        'series_id': 'PET.WCESTUS1.W',  # Gulf Coast specific
        'route': '/petroleum/stoc/wstk/data',
        'facets': {'series': 'W_EPC0_SAX_R30_MBBL'},
        'units': 'million barrels',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['crude', 'oil', 'stocks', 'inventory', 'gulf coast', 'padd 3', 'texas', 'louisiana'],
    },
    'eia_crude_stocks_cushing': {
        'name': 'Cushing OK Crude Oil Stocks',
        'description': 'Crude oil stocks at Cushing, Oklahoma - the WTI delivery point and key US storage hub (million barrels)',
        'series_id': 'PET.W_EPC0_SAX_YCUOK_MBBL.W',
        'route': '/petroleum/stoc/wstk/data',
        'facets': {'series': 'W_EPC0_SAX_YCUOK_MBBL'},
        'units': 'million barrels',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['crude', 'oil', 'stocks', 'cushing', 'oklahoma', 'wti', 'storage', 'hub'],
    },

    # ==========================================================================
    # DISTILLATE/HEATING OIL STOCKS
    # ==========================================================================
    'eia_distillate_stocks': {
        'name': 'US Distillate Fuel Oil Stocks',
        'description': 'Total US stocks of distillate fuel oil including diesel and heating oil (million barrels)',
        'series_id': 'PET.WDISTUS1.W',
        'route': '/petroleum/stoc/wstk/data',
        'facets': {'series': 'WDISTUS1'},
        'units': 'million barrels',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['distillate', 'diesel', 'heating oil', 'stocks', 'inventory', 'winter'],
    },

    # ==========================================================================
    # NATURAL GAS STORAGE AND PRODUCTION
    # ==========================================================================
    'eia_natural_gas_storage': {
        'name': 'US Natural Gas Working Storage',
        'description': 'Total US natural gas working underground storage in Lower 48 states, critical for winter heating supply (billion cubic feet)',
        'series_id': 'NG.NW2_EPG0_SWO_R48_BCF.W',
        'route': '/natural-gas/stor/wkly/data',
        'facets': {'series': 'NW2_EPG0_SWO_R48_BCF'},
        'units': 'billion cubic feet',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['natural gas', 'storage', 'inventory', 'heating', 'winter', 'supply'],
    },
    'eia_natural_gas_storage_east': {
        'name': 'East Region Natural Gas Storage',
        'description': 'Natural gas working underground storage in East region, important for Northeast winter heating (billion cubic feet)',
        'series_id': 'NG.NW2_EPG0_SWO_R31_BCF.W',
        'route': '/natural-gas/stor/wkly/data',
        'facets': {'series': 'NW2_EPG0_SWO_R31_BCF'},
        'units': 'billion cubic feet',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['natural gas', 'storage', 'east', 'northeast', 'heating', 'winter'],
    },
    'eia_natural_gas_storage_midwest': {
        'name': 'Midwest Region Natural Gas Storage',
        'description': 'Natural gas working underground storage in Midwest region (billion cubic feet)',
        'series_id': 'NG.NW2_EPG0_SWO_R32_BCF.W',
        'route': '/natural-gas/stor/wkly/data',
        'facets': {'series': 'NW2_EPG0_SWO_R32_BCF'},
        'units': 'billion cubic feet',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['natural gas', 'storage', 'midwest', 'heating', 'winter'],
    },
    'eia_natural_gas_production': {
        'name': 'US Natural Gas Marketed Production',
        'description': 'US marketed production of natural gas, measures domestic supply from shale and conventional wells (billion cubic feet)',
        'series_id': 'NG.N9050US2.M',
        'route': '/natural-gas/sum/lsum/data',
        'facets': {'series': 'N9050US2'},
        'units': 'billion cubic feet',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['natural gas', 'production', 'supply', 'shale', 'drilling'],
    },
    'eia_lng_exports': {
        'name': 'US LNG Exports',
        'description': 'US exports of liquefied natural gas (LNG), growing source of global gas supply (billion cubic feet)',
        'series_id': 'NG.N9130US1.M',
        'route': '/natural-gas/move/expu/data',
        'facets': {'series': 'N9130US1'},
        'units': 'billion cubic feet',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['lng', 'natural gas', 'exports', 'liquefied', 'trade', 'global'],
    },

    # ==========================================================================
    # ELECTRICITY GENERATION BY SOURCE
    # ==========================================================================
    'eia_electricity_generation_total': {
        'name': 'US Total Electricity Generation',
        'description': 'Total US electricity net generation from all fuel sources (thousand megawatthours)',
        'series_id': 'ELEC.GEN.ALL-US-99.M',
        'route': '/electricity/electric-power-operational-data/data',
        'facets': {'fueltypeid': 'ALL', 'location': 'US', 'sectorid': '99'},
        'units': 'thousand megawatthours',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'generation', 'power', 'total', 'grid'],
    },
    'eia_electricity_generation_nuclear': {
        'name': 'US Nuclear Electricity Generation',
        'description': 'US electricity generation from nuclear power plants, provides baseload zero-carbon power (thousand megawatthours)',
        'series_id': 'ELEC.GEN.NUC-US-99.M',
        'route': '/electricity/electric-power-operational-data/data',
        'facets': {'fueltypeid': 'NUC', 'location': 'US', 'sectorid': '99'},
        'units': 'thousand megawatthours',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'nuclear', 'generation', 'power', 'baseload', 'zero carbon'],
    },
    'eia_electricity_generation_natural_gas': {
        'name': 'US Natural Gas Electricity Generation',
        'description': 'US electricity generation from natural gas plants, largest source of US power (thousand megawatthours)',
        'series_id': 'ELEC.GEN.NG-US-99.M',
        'route': '/electricity/electric-power-operational-data/data',
        'facets': {'fueltypeid': 'NG', 'location': 'US', 'sectorid': '99'},
        'units': 'thousand megawatthours',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'natural gas', 'generation', 'power', 'gas turbine'],
    },
    'eia_electricity_generation_coal': {
        'name': 'US Coal Electricity Generation',
        'description': 'US electricity generation from coal-fired power plants, declining but still significant source (thousand megawatthours)',
        'series_id': 'ELEC.GEN.COW-US-99.M',
        'route': '/electricity/electric-power-operational-data/data',
        'facets': {'fueltypeid': 'COW', 'location': 'US', 'sectorid': '99'},
        'units': 'thousand megawatthours',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'coal', 'generation', 'power', 'fossil fuel'],
    },
    'eia_electricity_generation_wind': {
        'name': 'US Wind Electricity Generation',
        'description': 'US electricity generation from wind turbines, fastest growing renewable source (thousand megawatthours)',
        'series_id': 'ELEC.GEN.WND-US-99.M',
        'route': '/electricity/electric-power-operational-data/data',
        'facets': {'fueltypeid': 'WND', 'location': 'US', 'sectorid': '99'},
        'units': 'thousand megawatthours',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'wind', 'generation', 'renewable', 'clean energy', 'turbine'],
    },
    'eia_electricity_generation_solar': {
        'name': 'US Solar Electricity Generation',
        'description': 'US electricity generation from solar photovoltaic and thermal, rapidly expanding renewable source (thousand megawatthours)',
        'series_id': 'ELEC.GEN.SUN-US-99.M',
        'route': '/electricity/electric-power-operational-data/data',
        'facets': {'fueltypeid': 'SUN', 'location': 'US', 'sectorid': '99'},
        'units': 'thousand megawatthours',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'solar', 'generation', 'renewable', 'photovoltaic', 'pv', 'clean energy'],
    },
    'eia_electricity_generation_hydro': {
        'name': 'US Hydroelectric Generation',
        'description': 'US electricity generation from conventional hydroelectric dams, largest traditional renewable source (thousand megawatthours)',
        'series_id': 'ELEC.GEN.HYC-US-99.M',
        'route': '/electricity/electric-power-operational-data/data',
        'facets': {'fueltypeid': 'HYC', 'location': 'US', 'sectorid': '99'},
        'units': 'thousand megawatthours',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'hydro', 'hydroelectric', 'dam', 'renewable', 'water power'],
    },

    # ==========================================================================
    # COAL
    # ==========================================================================
    'eia_coal_production': {
        'name': 'US Coal Production',
        'description': 'Total US coal production from all mines, primary fossil fuel for power generation (thousand short tons)',
        'series_id': 'COAL.PRODUCTION.US-TOT.Q',
        'route': '/coal/mine/aggregate/data',
        'facets': {'location': 'US', 'coalRankId': 'TOT'},
        'units': 'thousand short tons',
        'frequency': 'quarterly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['coal', 'production', 'mining', 'fossil fuel', 'appalachia', 'powder river'],
    },
    'eia_coal_consumption_electric': {
        'name': 'US Coal Consumption for Electricity',
        'description': 'US coal consumption by electric power sector, primary use of coal in the economy (thousand short tons)',
        'series_id': 'COAL.CONS_TOT.US-94.Q',
        'route': '/coal/consumption-and-quality/data',
        'facets': {'location': 'US', 'sector': '94'},
        'units': 'thousand short tons',
        'frequency': 'quarterly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['coal', 'consumption', 'electricity', 'power plant', 'utility'],
    },
    'eia_coal_stocks_electric': {
        'name': 'US Electric Power Coal Stocks',
        'description': 'Coal stocks held by US electric power plants, indicates fuel security for power generation (thousand short tons)',
        'series_id': 'COAL.STOCKS.US-94.Q',
        'route': '/coal/consumption-and-quality/data',
        'facets': {'location': 'US', 'sector': '94'},
        'units': 'thousand short tons',
        'frequency': 'quarterly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['coal', 'stocks', 'inventory', 'power plant', 'utility', 'fuel security'],
    },

    # ==========================================================================
    # REGIONAL GASOLINE PRICES
    # ==========================================================================
    'eia_gasoline_east_coast': {
        'name': 'East Coast Gasoline Price',
        'description': 'Average retail gasoline price in East Coast (PADD 1) region ($/gallon)',
        'series_id': 'PET.EMM_EPM0_PTE_R10_DPG.W',
        'route': '/petroleum/pri/gnd/data',
        'facets': {'series': 'EMM_EPM0_PTE_R10_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gasoline', 'east coast', 'padd 1', 'fuel', 'regional', 'northeast'],
    },
    'eia_gasoline_gulf_coast': {
        'name': 'Gulf Coast Gasoline Price',
        'description': 'Average retail gasoline price in Gulf Coast (PADD 3) region including Texas ($/gallon)',
        'series_id': 'PET.EMM_EPM0_PTE_R30_DPG.W',
        'route': '/petroleum/pri/gnd/data',
        'facets': {'series': 'EMM_EPM0_PTE_R30_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gasoline', 'gulf coast', 'padd 3', 'texas', 'fuel', 'regional'],
    },
    'eia_gasoline_west_coast': {
        'name': 'West Coast Gasoline Price',
        'description': 'Average retail gasoline price in West Coast (PADD 5) region including California ($/gallon)',
        'series_id': 'PET.EMM_EPM0_PTE_R50_DPG.W',
        'route': '/petroleum/pri/gnd/data',
        'facets': {'series': 'EMM_EPM0_PTE_R50_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gasoline', 'west coast', 'padd 5', 'california', 'fuel', 'regional'],
    },
    'eia_gasoline_midwest': {
        'name': 'Midwest Gasoline Price',
        'description': 'Average retail gasoline price in Midwest (PADD 2) region ($/gallon)',
        'series_id': 'PET.EMM_EPM0_PTE_R20_DPG.W',
        'route': '/petroleum/pri/gnd/data',
        'facets': {'series': 'EMM_EPM0_PTE_R20_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gasoline', 'midwest', 'padd 2', 'fuel', 'regional'],
    },
    'eia_gasoline_california': {
        'name': 'California Gasoline Price',
        'description': 'Average retail gasoline price in California, typically highest in nation due to regulations ($/gallon)',
        'series_id': 'PET.EMM_EPM0_PTE_SCA_DPG.W',
        'route': '/petroleum/pri/gnd/data',
        'facets': {'series': 'EMM_EPM0_PTE_SCA_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gasoline', 'california', 'fuel', 'highest price', 'carb'],
    },

    # ==========================================================================
    # HEATING FUEL PRICES
    # ==========================================================================
    'eia_heating_oil_price': {
        'name': 'US Residential Heating Oil Price',
        'description': 'Average retail price of residential heating oil, critical for Northeast winter heating ($/gallon)',
        'series_id': 'PET.W_EPD2F_PRS_NUS_DPG.W',
        'route': '/petroleum/pri/wfr/data',
        'facets': {'series': 'W_EPD2F_PRS_NUS_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['heating oil', 'fuel oil', 'winter', 'heating', 'residential', 'northeast'],
    },
    'eia_propane_price': {
        'name': 'US Residential Propane Price',
        'description': 'Average retail price of residential propane, used for heating and rural energy ($/gallon)',
        'series_id': 'PET.W_EPLLPA_PRS_NUS_DPG.W',
        'route': '/petroleum/pri/wfr/data',
        'facets': {'series': 'W_EPLLPA_PRS_NUS_DPG'},
        'units': 'dollars per gallon',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['propane', 'lpg', 'heating', 'rural', 'residential', 'winter'],
    },

    # ==========================================================================
    # BIOFUELS
    # ==========================================================================
    'eia_ethanol_production': {
        'name': 'US Fuel Ethanol Production',
        'description': 'Weekly US oxygenate plant production of fuel ethanol, blended into gasoline (thousand barrels per day)',
        'series_id': 'PET.W_EPOOXE_YOP_NUS_MBBLD.W',
        'route': '/petroleum/sum/sndw/data',
        'facets': {'series': 'W_EPOOXE_YOP_NUS_MBBLD'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['ethanol', 'biofuel', 'renewable', 'corn', 'gasoline blend', 'e10', 'e15'],
    },
    'eia_ethanol_stocks': {
        'name': 'US Fuel Ethanol Stocks',
        'description': 'US stocks of fuel ethanol for gasoline blending (thousand barrels)',
        'series_id': 'PET.W_EPOOXE_SAE_NUS_MBBL.W',
        'route': '/petroleum/stoc/wstk/data',
        'facets': {'series': 'W_EPOOXE_SAE_NUS_MBBL'},
        'units': 'thousand barrels',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['ethanol', 'biofuel', 'stocks', 'inventory', 'renewable'],
    },

    # ==========================================================================
    # ELECTRICITY PRICES
    # ==========================================================================
    'eia_electricity_commercial': {
        'name': 'US Commercial Electricity Price',
        'description': 'Average retail price of electricity for commercial customers (cents/kWh)',
        'series_id': 'ELEC.PRICE.US-COM.M',
        'route': '/electricity/retail-sales/data',
        'facets': {'sectorid': 'COM', 'stateid': 'US'},
        'units': 'cents per kWh',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'commercial', 'business', 'power', 'utility'],
    },
    'eia_electricity_industrial': {
        'name': 'US Industrial Electricity Price',
        'description': 'Average retail price of electricity for industrial customers (cents/kWh)',
        'series_id': 'ELEC.PRICE.US-IND.M',
        'route': '/electricity/retail-sales/data',
        'facets': {'sectorid': 'IND', 'stateid': 'US'},
        'units': 'cents per kWh',
        'frequency': 'monthly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['electricity', 'industrial', 'manufacturing', 'power', 'utility'],
    },

    # ==========================================================================
    # PETROLEUM PRODUCTS SUPPLIED (DEMAND PROXY)
    # ==========================================================================
    'eia_gasoline_product_supplied': {
        'name': 'US Motor Gasoline Product Supplied',
        'description': 'Weekly US motor gasoline product supplied, proxy for gasoline demand (thousand barrels per day)',
        'series_id': 'PET.WGFUPUS2.W',
        'route': '/petroleum/sum/sndw/data',
        'facets': {'series': 'WGFUPUS2'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['gasoline', 'demand', 'consumption', 'driving', 'product supplied'],
    },
    'eia_distillate_product_supplied': {
        'name': 'US Distillate Product Supplied',
        'description': 'Weekly US distillate fuel product supplied, proxy for diesel and heating oil demand (thousand barrels per day)',
        'series_id': 'PET.WDIUPUS2.W',
        'route': '/petroleum/sum/sndw/data',
        'facets': {'series': 'WDIUPUS2'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['distillate', 'diesel', 'demand', 'trucking', 'product supplied', 'heating oil'],
    },
    'eia_jet_fuel_product_supplied': {
        'name': 'US Jet Fuel Product Supplied',
        'description': 'Weekly US kerosene-type jet fuel product supplied, indicator of air travel demand (thousand barrels per day)',
        'series_id': 'PET.WKJUPUS2.W',
        'route': '/petroleum/sum/sndw/data',
        'facets': {'series': 'WKJUPUS2'},
        'units': 'thousand barrels per day',
        'frequency': 'weekly',
        'measure_type': 'nominal',
        'change_type': 'level',
        'keywords': ['jet fuel', 'aviation', 'airline', 'travel', 'demand', 'product supplied'],
    },
}

# Cache
_cache = {}
_cache_ttl = timedelta(hours=1)


def _fetch_eia_v2(route: str, params: dict = None) -> dict:
    """
    Fetch data from EIA API v2.

    Args:
        route: API route (e.g., '/petroleum/pri/spt/data')
        params: Additional query parameters

    Returns:
        JSON response dict
    """
    if not EIA_API_KEY:
        print("[EIA] Warning: EIA_API_KEY not set. Get a free key at https://www.eia.gov/opendata/register.php")
        return {'error': 'No API key'}

    # Build URL
    url = f"{EIA_BASE_URL}{route}"
    query_parts = [f"api_key={EIA_API_KEY}"]

    if params:
        for key, value in params.items():
            if isinstance(value, dict):
                for k, v in value.items():
                    query_parts.append(f"facets[{k}][]={v}")
            elif isinstance(value, list):
                for v in value:
                    query_parts.append(f"{key}[]={v}")
            else:
                query_parts.append(f"{key}={value}")

    url = f"{url}?{'&'.join(query_parts)}"

    # Check cache
    cache_key = url
    now = datetime.now()
    if cache_key in _cache:
        cached_data, cached_time = _cache[cache_key]
        if now - cached_time < _cache_ttl:
            return cached_data

    try:
        req = Request(url, headers={'User-Agent': 'EconStats/1.0'})
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            _cache[cache_key] = (data, now)
            return data
    except URLError as e:
        print(f"[EIA] Error fetching {route}: {e}")
        return {'error': str(e)}
    except json.JSONDecodeError as e:
        print(f"[EIA] Invalid JSON response: {e}")
        return {'error': f"Invalid JSON: {e}"}


def _fetch_eia_legacy(series_id: str) -> dict:
    """
    Fetch data using legacy series ID (EIA API v1 compatibility).

    This uses the v2/seriesid endpoint which translates legacy series IDs.
    """
    if not EIA_API_KEY:
        print("[EIA] Warning: EIA_API_KEY not set.")
        return {'error': 'No API key'}

    url = f"{EIA_BASE_URL}/seriesid/{series_id}?api_key={EIA_API_KEY}"

    # Check cache
    cache_key = url
    now = datetime.now()
    if cache_key in _cache:
        cached_data, cached_time = _cache[cache_key]
        if now - cached_time < _cache_ttl:
            return cached_data

    try:
        req = Request(url, headers={'User-Agent': 'EconStats/1.0'})
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            _cache[cache_key] = (data, now)
            return data
    except URLError as e:
        print(f"[EIA] Error fetching series {series_id}: {e}")
        return {'error': str(e)}
    except json.JSONDecodeError as e:
        print(f"[EIA] Invalid JSON: {e}")
        return {'error': f"Invalid JSON: {e}"}


def get_eia_series(series_key: str) -> tuple:
    """
    Fetch an EIA series.

    Args:
        series_key: One of the keys in EIA_SERIES

    Returns:
        (dates, values, info) tuple compatible with FRED format
    """
    if series_key not in EIA_SERIES:
        return [], [], {'error': f"Unknown EIA series: {series_key}"}

    series_info = EIA_SERIES[series_key]
    series_id = series_info['series_id']

    # Try legacy endpoint (simpler, more reliable)
    data = _fetch_eia_legacy(series_id)

    if 'error' in data:
        return [], [], {'error': data['error']}

    # Parse response - v2 seriesid endpoint returns data in 'response' key
    response = data.get('response', {})
    if not response:
        # Try direct 'data' key
        response = data

    data_array = response.get('data', [])

    if not data_array:
        return [], [], {'error': 'No data returned from EIA'}

    # Extract dates and values
    # EIA returns data as list of dicts with 'period' and 'value' keys
    dates = []
    values = []

    for entry in data_array:
        period = entry.get('period')
        value = entry.get('value')

        if period and value is not None:
            try:
                # Period format varies: YYYY-MM-DD, YYYY-MM, YYYY
                if len(period) == 7:  # YYYY-MM
                    period = f"{period}-01"
                elif len(period) == 4:  # YYYY
                    period = f"{period}-01-01"

                dates.append(period)
                values.append(float(value))
            except (ValueError, TypeError):
                continue

    # EIA returns data newest first, reverse for chronological order
    dates = dates[::-1]
    values = values[::-1]

    info = {
        'id': series_key,
        'title': series_info['name'],
        'description': series_info['description'],
        'units': series_info['units'],
        'frequency': series_info['frequency'],
        'source': 'U.S. Energy Information Administration',
        'measure_type': series_info['measure_type'],
        'change_type': series_info['change_type'],
        'fred_equivalent': series_info.get('fred_equivalent'),
    }

    return dates, values, info


def search_eia_series(query: str) -> list:
    """
    Search for EIA series matching a query.

    Returns list of matching series keys.
    """
    query_lower = query.lower()
    matches = []

    for key, info in EIA_SERIES.items():
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
    """Return all available EIA series for catalog display."""
    return EIA_SERIES.copy()


def check_api_key() -> bool:
    """Check if EIA API key is configured."""
    return bool(EIA_API_KEY)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("Testing EIA data fetch...")
    print(f"API Key configured: {check_api_key()}")

    if not check_api_key():
        print("\nTo test, set EIA_API_KEY environment variable.")
        print("Get a free key at: https://www.eia.gov/opendata/register.php")
    else:
        # Test WTI crude
        print("\n1. Testing WTI Crude Oil Price:")
        dates, values, info = get_eia_series('eia_wti_crude')
        if dates:
            print(f"   Got {len(dates)} observations")
            print(f"   Latest: {dates[-1]} = ${values[-1]:.2f}/barrel")
        else:
            print(f"   Error: {info.get('error', 'Unknown error')}")

        # Test gasoline
        print("\n2. Testing Gasoline Retail Price:")
        dates, values, info = get_eia_series('eia_gasoline_retail')
        if dates:
            print(f"   Got {len(dates)} observations")
            print(f"   Latest: {dates[-1]} = ${values[-1]:.3f}/gallon")
        else:
            print(f"   Error: {info.get('error', 'Unknown error')}")

        # Test natural gas
        print("\n3. Testing Henry Hub Natural Gas:")
        dates, values, info = get_eia_series('eia_natural_gas_henry_hub')
        if dates:
            print(f"   Got {len(dates)} observations")
            print(f"   Latest: {dates[-1]} = ${values[-1]:.2f}/MMBtu")
        else:
            print(f"   Error: {info.get('error', 'Unknown error')}")

        # Test search
        print("\n4. Testing search for 'crude oil':")
        matches = search_eia_series("crude oil")
        print(f"   Matches: {matches}")


# =============================================================================
# NARRATIVE SYNTHESIS (Economist-style interpretation)
# =============================================================================

def synthesize_energy_narrative(
    wti_price: Optional[float] = None,
    wti_change_pct: Optional[float] = None,
    gasoline_price: Optional[float] = None,
    gasoline_change_pct: Optional[float] = None,
    natgas_price: Optional[float] = None,
    natgas_change_pct: Optional[float] = None,
    crude_stocks_change: Optional[float] = None,
) -> Optional[str]:
    """
    Synthesize energy data into a coherent narrative paragraph.

    Explains what energy prices mean for inflation, consumers, and the economy.

    Args:
        wti_price: WTI crude oil price ($/barrel)
        wti_change_pct: WTI year-over-year or week-over-week change (%)
        gasoline_price: Retail gasoline price ($/gallon)
        gasoline_change_pct: Gasoline price change (%)
        natgas_price: Natural gas price ($/MMBtu)
        natgas_change_pct: Natural gas price change (%)
        crude_stocks_change: Change in crude oil inventories (million barrels)

    Returns:
        Human-readable narrative about energy market conditions
    """
    parts = []

    # Oil price context
    if wti_price is not None:
        if wti_price < 60:
            parts.append(
                f"Oil at ${wti_price:.0f}/barrel is unusually cheap by recent standards, "
                "helping keep inflation in check. Sub-$60 oil typically signals weak global demand "
                "or an oversupplied market."
            )
        elif wti_price < 75:
            parts.append(
                f"Oil prices around ${wti_price:.0f}/barrel are in a comfortable range for the economy—"
                "high enough for producers to profit, low enough to avoid stoking inflation."
            )
        elif wti_price < 90:
            parts.append(
                f"At ${wti_price:.0f}/barrel, oil is elevated but manageable. "
                "This adds about 0.1-0.2pp to headline CPI compared to the $70 level, "
                "but won't derail the Fed's inflation fight."
            )
        else:
            parts.append(
                f"Oil at ${wti_price:.0f}/barrel is a headwind for inflation. "
                "Prices above $90 typically add 0.3-0.5pp to CPI and act as a tax on consumers, "
                "potentially slowing economic growth."
            )

    # Gasoline impact on consumers
    if gasoline_price is not None:
        # Average American drives ~12,000 miles/year, gets ~25 mpg = 480 gallons/year
        # Every $1/gallon = $480/year or $40/month
        if gasoline_price < 3.0:
            parts.append(
                f"Gasoline at ${gasoline_price:.2f}/gallon is a tailwind for consumers—"
                "well below the $3.50+ levels that strain budgets. "
                "This leaves more room for discretionary spending."
            )
        elif gasoline_price < 3.5:
            parts.append(
                f"Gas prices at ${gasoline_price:.2f}/gallon are moderate, "
                "roughly in line with historical averages when adjusted for inflation."
            )
        elif gasoline_price < 4.0:
            parts.append(
                f"At ${gasoline_price:.2f}/gallon, gas is elevated and noticeable to consumers. "
                "The typical household spends about $40/month more compared to $3.00 gas."
            )
        else:
            parts.append(
                f"Gasoline at ${gasoline_price:.2f}/gallon is a significant burden—"
                "a typical family pays $600+/year more than when gas was $3. "
                "High pump prices hurt consumer sentiment and can slow spending."
            )

    # Natural gas (heating/electricity costs)
    if natgas_price is not None:
        if natgas_price < 2.5:
            parts.append(
                f"Natural gas at ${natgas_price:.2f}/MMBtu is extremely cheap, "
                "keeping electricity and heating costs low. "
                "This is good for inflation but tough for gas producers."
            )
        elif natgas_price < 4.0:
            parts.append(
                f"Natural gas around ${natgas_price:.2f}/MMBtu is well-contained, "
                "posing no threat to utility bills or industrial costs."
            )
        elif natgas_price < 6.0:
            parts.append(
                f"Natural gas at ${natgas_price:.2f}/MMBtu is elevated, "
                "which flows through to electricity prices with a lag of a few months."
            )
        else:
            parts.append(
                f"At ${natgas_price:.2f}/MMBtu, natural gas is expensive enough to impact "
                "utility bills and industrial costs. Prolonged high prices add to inflation pressures."
            )

    # Inventory signal
    if crude_stocks_change is not None:
        if abs(crude_stocks_change) > 5:
            direction = "building" if crude_stocks_change > 0 else "drawing"
            parts.append(
                f"Crude inventories are {direction} significantly ({crude_stocks_change:+.1f}M barrels), "
                f"{'suggesting demand is softening.' if crude_stocks_change > 0 else 'signaling tight supply.'}"
            )

    if not parts:
        return None

    return " ".join(parts)


def get_energy_narrative() -> Optional[str]:
    """
    Convenience function to fetch current EIA data and synthesize narrative.

    Requires EIA_API_KEY to be set.

    Returns:
        Synthesized narrative about current energy conditions, or None on error.
    """
    if not check_api_key():
        return None

    # Fetch current data
    _, wti_values, _ = get_eia_series('eia_wti_crude')
    _, gas_values, _ = get_eia_series('eia_gasoline_retail')
    _, natgas_values, _ = get_eia_series('eia_natural_gas_henry_hub')

    # Get latest values
    wti_price = wti_values[-1] if wti_values else None
    gasoline_price = gas_values[-1] if gas_values else None
    natgas_price = natgas_values[-1] if natgas_values else None

    return synthesize_energy_narrative(
        wti_price=wti_price,
        gasoline_price=gasoline_price,
        natgas_price=natgas_price,
    )
