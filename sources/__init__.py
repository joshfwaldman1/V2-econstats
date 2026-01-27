"""Data sources module - Unified interface for all data providers."""

from .base import DataSource, SeriesData
from .fred import FREDSource
from .manager import DataSourceManager, source_manager

__all__ = ['DataSource', 'SeriesData', 'FREDSource', 'DataSourceManager', 'source_manager']
