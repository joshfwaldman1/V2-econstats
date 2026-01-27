"""
FRED Data Source - Federal Reserve Economic Data

Primary source for most US economic data series.
"""

import httpx
from datetime import datetime, timedelta
from typing import Optional, List

from .base import DataSource, SeriesData
from config import config


class FREDSource(DataSource):
    """Data source for FRED (Federal Reserve Economic Data)."""

    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or config.fred_api_key

    @property
    def name(self) -> str:
        return "FRED"

    def supports(self, series_id: str) -> bool:
        """
        FRED supports most uppercase alphanumeric series IDs.
        We use this as the default/fallback source.
        """
        # FRED series are typically uppercase alphanumeric
        # This source acts as the primary/default
        if not series_id:
            return False

        # Exclude known non-FRED prefixes
        non_fred_prefixes = ['zillow_', 'av_', 'eia_', 'dbnomics/', 'shiller_']
        for prefix in non_fred_prefixes:
            if series_id.lower().startswith(prefix):
                return False

        return True

    async def fetch(self, series_id: str, years: int = 5) -> SeriesData:
        """Fetch data from FRED API."""
        if not self._api_key:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error="FRED API key not configured"
            )

        # Calculate date range
        end_date = datetime.now()
        if years:
            start_date = end_date - timedelta(days=years * 365)
        else:
            start_date = datetime(1950, 1, 1)  # All available data

        # Fetch series info and observations
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Fetch observations
                obs_url = f"{self.BASE_URL}/series/observations"
                obs_params = {
                    'series_id': series_id,
                    'api_key': self._api_key,
                    'file_type': 'json',
                    'observation_start': start_date.strftime('%Y-%m-%d'),
                    'observation_end': end_date.strftime('%Y-%m-%d'),
                }

                obs_resp = await client.get(obs_url, params=obs_params)
                obs_data = obs_resp.json()

                if 'error_message' in obs_data:
                    return SeriesData(
                        id=series_id,
                        dates=[],
                        values=[],
                        error=obs_data.get('error_message', 'Unknown error')
                    )

                # Fetch series info
                info_url = f"{self.BASE_URL}/series"
                info_params = {
                    'series_id': series_id,
                    'api_key': self._api_key,
                    'file_type': 'json',
                }

                info_resp = await client.get(info_url, params=info_params)
                info_data = info_resp.json()

                # Parse observations
                dates = []
                values = []
                for obs in obs_data.get('observations', []):
                    if obs.get('value') and obs['value'] != '.':
                        try:
                            dates.append(obs['date'])
                            values.append(float(obs['value']))
                        except (ValueError, TypeError):
                            continue

                # Build info dict
                series_info = info_data.get('seriess', [{}])[0] if info_data.get('seriess') else {}
                info = {
                    'name': series_info.get('title', series_id),
                    'title': series_info.get('title', series_id),
                    'unit': series_info.get('units', ''),
                    'units': series_info.get('units', ''),
                    'frequency': series_info.get('frequency', 'Monthly'),
                    'seasonal_adjustment': series_info.get('seasonal_adjustment_short', ''),
                    'source': 'FRED',
                    'last_updated': series_info.get('last_updated', ''),
                }

                return SeriesData(
                    id=series_id,
                    dates=dates,
                    values=values,
                    info=info
                )

        except httpx.TimeoutException:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error=f"Timeout fetching {series_id} from FRED"
            )
        except Exception as e:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error=f"Error fetching {series_id}: {str(e)}"
            )

    def fetch_sync(self, series_id: str, years: int = 5) -> SeriesData:
        """Synchronous version using httpx sync client."""
        if not self._api_key:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error="FRED API key not configured"
            )

        end_date = datetime.now()
        if years:
            start_date = end_date - timedelta(days=years * 365)
        else:
            start_date = datetime(1950, 1, 1)

        try:
            with httpx.Client(timeout=15.0) as client:
                # Fetch observations
                obs_url = f"{self.BASE_URL}/series/observations"
                obs_params = {
                    'series_id': series_id,
                    'api_key': self._api_key,
                    'file_type': 'json',
                    'observation_start': start_date.strftime('%Y-%m-%d'),
                    'observation_end': end_date.strftime('%Y-%m-%d'),
                }

                obs_resp = client.get(obs_url, params=obs_params)
                obs_data = obs_resp.json()

                if 'error_message' in obs_data:
                    return SeriesData(
                        id=series_id,
                        dates=[],
                        values=[],
                        error=obs_data.get('error_message', 'Unknown error')
                    )

                # Fetch series info
                info_url = f"{self.BASE_URL}/series"
                info_params = {
                    'series_id': series_id,
                    'api_key': self._api_key,
                    'file_type': 'json',
                }

                info_resp = client.get(info_url, params=info_params)
                info_data = info_resp.json()

                # Parse observations
                dates = []
                values = []
                for obs in obs_data.get('observations', []):
                    if obs.get('value') and obs['value'] != '.':
                        try:
                            dates.append(obs['date'])
                            values.append(float(obs['value']))
                        except (ValueError, TypeError):
                            continue

                # Build info dict
                series_info = info_data.get('seriess', [{}])[0] if info_data.get('seriess') else {}
                info = {
                    'name': series_info.get('title', series_id),
                    'title': series_info.get('title', series_id),
                    'unit': series_info.get('units', ''),
                    'units': series_info.get('units', ''),
                    'frequency': series_info.get('frequency', 'Monthly'),
                    'seasonal_adjustment': series_info.get('seasonal_adjustment_short', ''),
                    'source': 'FRED',
                    'last_updated': series_info.get('last_updated', ''),
                }

                return SeriesData(
                    id=series_id,
                    dates=dates,
                    values=values,
                    info=info
                )

        except httpx.TimeoutException:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error=f"Timeout fetching {series_id} from FRED"
            )
        except Exception as e:
            return SeriesData(
                id=series_id,
                dates=[],
                values=[],
                error=f"Error fetching {series_id}: {str(e)}"
            )

    async def search(self, query: str, limit: int = 10) -> List[dict]:
        """Search FRED for series matching a query."""
        if not self._api_key:
            return []

        url = f"{self.BASE_URL}/series/search"
        params = {
            'search_text': query,
            'api_key': self._api_key,
            'file_type': 'json',
            'limit': limit,
            'order_by': 'popularity',
            'sort_order': 'desc',
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                data = resp.json()

                results = []
                for s in data.get('seriess', []):
                    results.append({
                        'series_id': s['id'],
                        'title': s['title'],
                        'frequency': s.get('frequency', 'Unknown'),
                        'units': s.get('units', ''),
                        'seasonal_adjustment': s.get('seasonal_adjustment_short', ''),
                        'popularity': s.get('popularity', 0),
                    })
                return results
        except Exception as e:
            print(f"FRED search error: {e}")
            return []
