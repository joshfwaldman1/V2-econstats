"""
Data Source Manager - Routes series IDs to appropriate sources.

Provides unified interface for fetching data from any supported source.
"""

from typing import List, Optional
import asyncio

from .base import DataSource, SeriesData
from .fred import FREDSource
from cache import cache_manager


class DataSourceManager:
    """
    Routes series IDs to appropriate data sources.

    Handles caching, parallel fetching, and fallback logic.
    """

    def __init__(self):
        # Register data sources in priority order
        self._sources: List[DataSource] = [
            FREDSource(),  # Primary source
            # Future sources can be added here:
            # AlphaVantageSource(),
            # ZillowSource(),
            # EIASource(),
            # DBnomicsSource(),
        ]

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

    def available_sources(self) -> List[str]:
        """Get names of all registered data sources."""
        return [s.name for s in self._sources]


# Global instance
source_manager = DataSourceManager()
