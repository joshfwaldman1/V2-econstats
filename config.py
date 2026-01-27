"""
EconStats V2 - Centralized Configuration

All environment variables, constants, and settings in one place.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Application configuration loaded from environment."""

    # API Keys
    fred_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    alphavantage_api_key: Optional[str] = None

    # Cache settings
    routing_cache_ttl: int = 3600      # 1 hour
    data_cache_ttl: int = 1800         # 30 minutes
    summary_cache_ttl: int = 3600      # 1 hour
    bullet_cache_ttl: int = 86400      # 24 hours
    max_cache_size: int = 10000

    # LLM settings
    default_model: str = "claude-sonnet-4-20250514"
    max_llm_calls_per_request: int = 2
    enable_economist_reviewer: bool = False  # Off by default to save costs
    enable_dynamic_bullets: bool = False     # Use static bullets by default
    enable_gemini_audit: bool = True         # Fast Gemini-auditing-Gemini layer

    # Data settings
    default_years: int = 8
    max_years: int = 50

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            fred_api_key=os.environ.get('FRED_API_KEY'),
            anthropic_api_key=os.environ.get('ANTHROPIC_API_KEY'),
            google_api_key=os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY'),
            alphavantage_api_key=os.environ.get('ALPHAVANTAGE_API_KEY'),

            # Allow override via env
            routing_cache_ttl=int(os.environ.get('ROUTING_CACHE_TTL', 3600)),
            data_cache_ttl=int(os.environ.get('DATA_CACHE_TTL', 1800)),
            enable_economist_reviewer=os.environ.get('ENABLE_ECONOMIST_REVIEWER', '').lower() == 'true',
            enable_dynamic_bullets=os.environ.get('ENABLE_DYNAMIC_BULLETS', '').lower() == 'true',
            enable_gemini_audit=os.environ.get('ENABLE_GEMINI_AUDIT', 'true').lower() != 'false',  # On by default
        )


# Global config instance
config = Config.from_env()


# NBER Recession dates (for chart shading)
RECESSIONS = [
    ('1948-11-01', '1949-10-01'),
    ('1953-07-01', '1954-05-01'),
    ('1957-08-01', '1958-04-01'),
    ('1960-04-01', '1961-02-01'),
    ('1969-12-01', '1970-11-01'),
    ('1973-11-01', '1975-03-01'),
    ('1980-01-01', '1980-07-01'),
    ('1981-07-01', '1982-11-01'),
    ('1990-07-01', '1991-03-01'),
    ('2001-03-01', '2001-11-01'),
    ('2007-12-01', '2009-06-01'),
    ('2020-02-01', '2020-04-01'),
]


# Economic events for annotations
ECONOMIC_EVENTS = [
    {'date': '2022-03-17', 'label': 'Fed hikes begin', 'type': 'fed'},
    {'date': '2020-03-15', 'label': 'Emergency cut to 0%', 'type': 'fed'},
    {'date': '2019-07-31', 'label': 'Fed cuts rates', 'type': 'fed'},
    {'date': '2015-12-16', 'label': 'First hike since 2008', 'type': 'fed'},
    {'date': '2008-12-16', 'label': 'Fed cuts to zero', 'type': 'fed'},
    {'date': '2024-09-18', 'label': 'Fed starts cutting', 'type': 'fed'},
    {'date': '2022-06-01', 'label': 'Inflation peaks 9.1%', 'type': 'crisis'},
    {'date': '2020-04-01', 'label': 'Unemployment hits 14.7%', 'type': 'crisis'},
    {'date': '2020-03-11', 'label': 'COVID pandemic', 'type': 'crisis'},
    {'date': '2023-03-10', 'label': 'SVB collapse', 'type': 'crisis'},
    {'date': '2008-09-15', 'label': 'Lehman collapse', 'type': 'crisis'},
    {'date': '2017-12-22', 'label': 'Tax Cuts Act', 'type': 'policy'},
    {'date': '2021-03-11', 'label': 'ARP stimulus', 'type': 'policy'},
    {'date': '2022-08-16', 'label': 'IRA signed', 'type': 'policy'},
]


# US States for geographic detection
US_STATES = {
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
    'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
    'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
    'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
    'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
    'new hampshire', 'new jersey', 'new mexico', 'new york',
    'north carolina', 'north dakota', 'ohio', 'oklahoma', 'oregon',
    'pennsylvania', 'rhode island', 'south carolina', 'south dakota',
    'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington',
    'west virginia', 'wisconsin', 'wyoming'
}

US_REGIONS = {'midwest', 'northeast', 'south', 'west', 'pacific', 'mountain', 'southeast', 'southwest'}
