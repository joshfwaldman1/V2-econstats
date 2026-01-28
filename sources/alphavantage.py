"""
Alpha Vantage Data Source - Stocks, forex, P/E ratios.

Wraps the existing agents/alphavantage.py module.
"""

from typing import Optional, List
from .base import DataSource, SeriesData
from config import config


class AlphaVantageSource(DataSource):
    """Data source for Alpha Vantage (stocks, forex, etc.)."""

    def __init__(self):
        self._module = None
        self._available = False
        self._load_module()

    def _load_module(self):
        """Lazy load the alphavantage module."""
        try:
            from agents.alphavantage import get_alphavantage_series, ALPHAVANTAGE_SERIES
            self._module = {
                'get_series': get_alphavantage_series,
                'series_list': ALPHAVANTAGE_SERIES,
            }
            self._available = True
        except Exception as e:
            print(f"[AlphaVantage] Module not available: {e}")
            self._available = False

    @property
    def name(self) -> str:
        return "Alpha Vantage"

    @property
    def available(self) -> bool:
        return self._available

    def supports(self, series_id: str) -> bool:
        """Check if this is an Alpha Vantage series."""
        if not self._available:
            return False

        # Check if in known series list (explicit Alpha Vantage series)
        if series_id in self._module.get('series_list', {}):
            return True

        # Check for stock ticker pattern (uppercase letters, 1-5 chars)
        # BUT exclude known FRED series patterns that look like tickers:
        #   - State unemployment rates: {2-letter state}UR (NYUR, CAUR, TXUR)
        #   - State nonfarm payrolls: {2-letter state}NA (NYNA, CANA, TXNA)
        #   - Common FRED series: UNRATE, PAYEMS, etc.
        if series_id.isupper() and 1 <= len(series_id) <= 5:
            # Exclude FRED state economic series patterns
            if len(series_id) == 4:
                suffix = series_id[2:]
                # State unemployment ({ST}UR), state payrolls ({ST}NA),
                # state labor force ({ST}LF), state participation ({ST}PR)
                if suffix in ('UR', 'NA', 'LF', 'PR'):
                    return False

            # Exclude well-known short FRED series
            known_fred = {
                'GDP', 'GNP', 'PCE', 'CPI', 'PPI',
                'M1', 'M2', 'M1SL', 'M2SL',
                'BASE', 'BOGMB',
                'HOUST', 'RSAFS', 'DSPI',
                'DTWEXB', 'NAPM', 'UMCSENT',
            }
            if series_id in known_fred:
                return False

            # Likely a stock ticker
            return True

        return False

    async def fetch(self, series_id: str, years: int = 5) -> SeriesData:
        """Fetch data from Alpha Vantage."""
        return self.fetch_sync(series_id, years)

    def fetch_sync(self, series_id: str, years: int = 5) -> SeriesData:
        """Synchronous fetch from Alpha Vantage."""
        if not self._available:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error="Alpha Vantage module not available"
            )

        try:
            get_series = self._module['get_series']
            dates, values, info = get_series(series_id, years=years)

            if dates and values:
                return SeriesData(
                    id=series_id,
                    dates=dates,
                    values=values,
                    info=info or {}
                )
            else:
                return SeriesData(
                    id=series_id,
                    dates=[],
                    values=[],
                    error=f"No data returned for {series_id}"
                )

        except Exception as e:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error=f"Error fetching {series_id}: {str(e)}"
            )

    def get_series_list(self) -> dict:
        """Get available Alpha Vantage series."""
        if self._available:
            return self._module.get('series_list', {})
        return {}
