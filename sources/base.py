"""
Abstract interface for all data sources.

Makes it trivial to add new data sources - just implement the DataSource protocol.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class SeriesData:
    """Result from fetching a data series."""

    id: str
    dates: List[str]
    values: List[float]
    info: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if data was fetched successfully."""
        return self.error is None and len(self.dates) > 0 and len(self.values) > 0

    @property
    def latest(self) -> Optional[float]:
        """Get most recent value."""
        return self.values[-1] if self.values else None

    @property
    def latest_date(self) -> Optional[str]:
        """Get most recent date."""
        return self.dates[-1] if self.dates else None


class DataSource(ABC):
    """Abstract base class for data sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this data source."""
        pass

    @abstractmethod
    async def fetch(self, series_id: str, years: int = 5) -> SeriesData:
        """
        Fetch data for a single series.

        Args:
            series_id: The identifier for the series
            years: Number of years of historical data to fetch

        Returns:
            SeriesData with dates, values, and metadata
        """
        pass

    @abstractmethod
    def supports(self, series_id: str) -> bool:
        """
        Check if this source handles the given series ID.

        Args:
            series_id: The identifier to check

        Returns:
            True if this source can fetch the series
        """
        pass

    def fetch_sync(self, series_id: str, years: int = 5) -> SeriesData:
        """
        Synchronous version of fetch for backward compatibility.

        Default implementation runs the async method in an event loop.
        Override for sources that don't support async.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.fetch(series_id, years))
