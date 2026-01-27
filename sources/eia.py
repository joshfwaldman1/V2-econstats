"""
EIA Data Source - Energy data.

Wraps the existing agents/eia.py module.
"""

from .base import DataSource, SeriesData


class EIASource(DataSource):
    """Data source for EIA energy data."""

    def __init__(self):
        self._module = None
        self._available = False
        self._load_module()

    def _load_module(self):
        try:
            from agents.eia import get_eia_series, EIA_SERIES
            self._module = {
                'get_series': get_eia_series,
                'series_list': EIA_SERIES,
            }
            self._available = True
        except Exception as e:
            print(f"[EIA] Module not available: {e}")
            self._available = False

    @property
    def name(self) -> str:
        return "EIA"

    @property
    def available(self) -> bool:
        return self._available

    def supports(self, series_id: str) -> bool:
        if not self._available:
            return False
        if series_id.lower().startswith('eia_'):
            return True
        if series_id in self._module.get('series_list', {}):
            return True
        return False

    async def fetch(self, series_id: str, years: int = 5) -> SeriesData:
        return self.fetch_sync(series_id, years)

    def fetch_sync(self, series_id: str, years: int = 5) -> SeriesData:
        if not self._available:
            return SeriesData(id=series_id, dates=[], values=[], error="EIA module not available")

        try:
            get_series = self._module['get_series']
            dates, values, info = get_series(series_id, years=years)

            if dates and values:
                return SeriesData(id=series_id, dates=dates, values=values, info=info or {})
            return SeriesData(id=series_id, dates=[], values=[], error=f"No data for {series_id}")

        except Exception as e:
            return SeriesData(id=series_id, dates=[], values=[], error=str(e))
