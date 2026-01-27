"""
Shiller Data Source - CAPE ratio and valuation data.

Wraps the existing agents/shiller.py module.
"""

from .base import DataSource, SeriesData


class ShillerSource(DataSource):
    """Data source for Shiller CAPE valuation data."""

    def __init__(self):
        self._module = None
        self._available = False
        self._load_module()

    def _load_module(self):
        try:
            from agents.shiller import (
                get_cape_series,
                get_current_cape,
                get_bubble_comparison_data,
                is_valuation_query
            )
            self._module = {
                'get_cape_series': get_cape_series,
                'get_current_cape': get_current_cape,
                'get_bubble_comparison': get_bubble_comparison_data,
                'is_valuation_query': is_valuation_query,
            }
            self._available = True
        except Exception as e:
            print(f"[Shiller] Module not available: {e}")
            self._available = False

    @property
    def name(self) -> str:
        return "Shiller"

    @property
    def available(self) -> bool:
        return self._available

    def supports(self, series_id: str) -> bool:
        if not self._available:
            return False
        series_lower = series_id.lower()
        return series_lower in ('cape', 'shiller_cape', 'cape_ratio', 'shiller_pe')

    async def fetch(self, series_id: str, years: int = 5) -> SeriesData:
        return self.fetch_sync(series_id, years)

    def fetch_sync(self, series_id: str, years: int = 5) -> SeriesData:
        if not self._available:
            return SeriesData(id=series_id, dates=[], values=[], error="Shiller module not available")

        try:
            # get_cape_series returns dict with 'dates', 'values', 'info'
            get_cape = self._module['get_cape_series']
            cape_data = get_cape()  # Returns full history, we filter below

            dates = cape_data.get('dates', [])
            values = cape_data.get('values', [])
            info = cape_data.get('info', {})

            # Filter to requested years (data is monthly)
            if years and len(dates) > years * 12:
                dates = dates[-(years * 12):]
                values = values[-(years * 12):]

            if dates and values:
                return SeriesData(
                    id=series_id,
                    dates=dates,
                    values=values,
                    info={
                        'name': info.get('title', 'Shiller CAPE Ratio'),
                        'title': info.get('title', 'Shiller CAPE Ratio'),
                        'unit': info.get('units', 'Ratio'),
                        'units': info.get('units', 'Ratio'),
                        'source': info.get('source', 'Robert Shiller, Yale University'),
                        'notes': info.get('notes', ''),
                        'frequency': info.get('frequency', 'Monthly'),
                    }
                )

            return SeriesData(id=series_id, dates=[], values=[], error="No CAPE data")

        except Exception as e:
            return SeriesData(id=series_id, dates=[], values=[], error=str(e))

    def get_current_cape(self) -> dict:
        """Get current CAPE ratio and context."""
        if not self._available:
            return {}
        try:
            return self._module['get_current_cape']()
        except:
            return {}

    def get_bubble_comparison(self) -> dict:
        """Get bubble comparison data."""
        if not self._available:
            return {}
        try:
            return self._module['get_bubble_comparison']()
        except:
            return {}

    def is_valuation_query(self, query: str) -> bool:
        """Check if query is about valuation/CAPE."""
        if not self._available:
            return False
        try:
            return self._module['is_valuation_query'](query)
        except:
            return False
