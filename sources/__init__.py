"""Data sources module - Unified interface for all data providers."""

from .base import DataSource, SeriesData
from .fred import FREDSource
from .alphavantage import AlphaVantageSource
from .zillow import ZillowSource
from .eia import EIASource
from .dbnomics import DBnomicsSource
from .shiller import ShillerSource
from .manager import DataSourceManager, source_manager

__all__ = [
    'DataSource',
    'SeriesData',
    'FREDSource',
    'AlphaVantageSource',
    'ZillowSource',
    'EIASource',
    'DBnomicsSource',
    'ShillerSource',
    'DataSourceManager',
    'source_manager',
]
