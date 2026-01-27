"""
DBnomics Data Source - International economic data.

Wraps the existing agents/dbnomics.py module.
"""

from .base import DataSource, SeriesData


class DBnomicsSource(DataSource):
    """Data source for DBnomics international data."""

    def __init__(self):
        self._module = None
        self._available = False
        self._load_module()

    def _load_module(self):
        try:
            from agents.dbnomics import get_observations_dbnomics, INTERNATIONAL_SERIES, INTERNATIONAL_QUERY_PLANS
            self._module = {
                'get_series': get_observations_dbnomics,
                'series_list': INTERNATIONAL_SERIES,
                'query_plans': INTERNATIONAL_QUERY_PLANS,
            }
            self._available = True
        except Exception as e:
            print(f"[DBnomics] Module not available: {e}")
            self._available = False

    @property
    def name(self) -> str:
        return "DBnomics"

    @property
    def available(self) -> bool:
        return self._available

    def supports(self, series_id: str) -> bool:
        if not self._available:
            return False
        # DBnomics series have format like "provider/dataset/series"
        if '/' in series_id:
            return True
        if series_id in self._module.get('series_list', {}):
            return True
        return False

    async def fetch(self, series_id: str, years: int = 5) -> SeriesData:
        return self.fetch_sync(series_id, years)

    def fetch_sync(self, series_id: str, years: int = 5) -> SeriesData:
        if not self._available:
            return SeriesData(id=series_id, dates=[], values=[], error="DBnomics module not available")

        try:
            get_series = self._module['get_series']
            result = get_series(series_id, years=years)

            if result and len(result) >= 2:
                dates, values = result[0], result[1]
                info = result[2] if len(result) > 2 else {}

                if dates and values:
                    return SeriesData(id=series_id, dates=dates, values=values, info=info)

            return SeriesData(id=series_id, dates=[], values=[], error=f"No data for {series_id}")

        except Exception as e:
            return SeriesData(id=series_id, dates=[], values=[], error=str(e))

    def get_query_plans(self) -> dict:
        """Get international query plans."""
        if self._available:
            return self._module.get('query_plans', {})
        return {}
