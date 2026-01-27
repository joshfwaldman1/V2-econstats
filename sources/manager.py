"""
Data Source Manager - Routes series IDs to appropriate sources.

Provides unified interface for fetching data from any supported source.
"""

from typing import List, Optional
import asyncio

from .base import DataSource, SeriesData
from .fred import FREDSource
from .alphavantage import AlphaVantageSource
from .zillow import ZillowSource
from .eia import EIASource
from .dbnomics import DBnomicsSource
from .shiller import ShillerSource
from cache import cache_manager


class DataSourceManager:
    """
    Routes series IDs to appropriate data sources.

    Handles caching, parallel fetching, and fallback logic.
    """

    def __init__(self):
        # Register data sources in priority order (specialized first, FRED as fallback)
        self._sources: List[DataSource] = []
        self._source_status = {}
        self._initialize_sources()

    def _initialize_sources(self):
        """Initialize all data sources."""
        # Specialized sources first (they have explicit support() checks)
        source_classes = [
            ('alphavantage', AlphaVantageSource),
            ('zillow', ZillowSource),
            ('eia', EIASource),
            ('dbnomics', DBnomicsSource),
            ('shiller', ShillerSource),
            ('fred', FREDSource),  # FRED last as catch-all
        ]

        for name, cls in source_classes:
            try:
                source = cls()
                self._sources.append(source)
                self._source_status[name] = getattr(source, 'available', True)
                print(f"[Sources] {source.name}: {'available' if self._source_status[name] else 'not available'}")
            except Exception as e:
                print(f"[Sources] {name}: failed to initialize - {e}")
                self._source_status[name] = False

    def get_source(self, series_id: str) -> Optional[DataSource]:
        """Find the data source that handles a series ID."""
        for source in self._sources:
            if source.supports(series_id):
                return source
        return None

    async def fetch(self, series_id: str, years: int = 5) -> SeriesData:
        """
        Fetch data for a series, using cache if available.

        Args:
            series_id: The series identifier
            years: Number of years of data

        Returns:
            SeriesData with dates, values, info
        """
        # Check cache first
        cached = cache_manager.get_data(series_id, years)
        if cached:
            dates, values, info = cached
            return SeriesData(id=series_id, dates=dates, values=values, info=info)

        # Find appropriate source
        source = self.get_source(series_id)
        if not source:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error=f"No data source found for {series_id}"
            )

        # Fetch from source
        result = await source.fetch(series_id, years)

        # Cache successful results
        if result.is_valid:
            cache_manager.set_data(series_id, years, result.dates, result.values, result.info)

        return result

    def fetch_sync(self, series_id: str, years: int = 5) -> SeriesData:
        """Synchronous fetch - uses cache and sync source methods."""
        # Check cache first
        cached = cache_manager.get_data(series_id, years)
        if cached:
            dates, values, info = cached
            return SeriesData(id=series_id, dates=dates, values=values, info=info)

        # Find source
        source = self.get_source(series_id)
        if not source:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error=f"No data source found for {series_id}"
            )

        # Fetch synchronously
        result = source.fetch_sync(series_id, years)

        # Cache successful results
        if result.is_valid:
            cache_manager.set_data(series_id, years, result.dates, result.values, result.info)

        return result

    async def fetch_many(self, series_ids: List[str], years: int = 5) -> List[SeriesData]:
        """
        Fetch multiple series in parallel.

        Args:
            series_ids: List of series identifiers
            years: Number of years of data

        Returns:
            List of SeriesData in same order as input
        """
        tasks = [self.fetch(sid, years) for sid in series_ids]
        return await asyncio.gather(*tasks)

    def fetch_many_sync(self, series_ids: List[str], years: int = 5) -> List[SeriesData]:
        """Synchronous version of fetch_many."""
        return [self.fetch_sync(sid, years) for sid in series_ids]

    def available_sources(self) -> dict:
        """Get status of all registered data sources."""
        return dict(self._source_status)

    def get_shiller_source(self) -> Optional[ShillerSource]:
        """Get the Shiller source for special CAPE queries."""
        for source in self._sources:
            if isinstance(source, ShillerSource):
                return source
        return None

    def get_dbnomics_source(self) -> Optional[DBnomicsSource]:
        """Get the DBnomics source for international query plans."""
        for source in self._sources:
            if isinstance(source, DBnomicsSource):
                return source
        return None


# Global instance
source_manager = DataSourceManager()
