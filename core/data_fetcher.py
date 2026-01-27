"""
Unified Data Fetcher - Single interface for all data sources.

Routes requests to FRED, DBnomics, or other sources based on series metadata.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from .series_catalog import SERIES_CATALOG, get_series_metadata

# FRED API configuration
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FRED_API_BASE = "https://api.stlouisfed.org/fred"

# DBnomics API configuration
DBNOMICS_API = "https://api.db.nomics.world/v22"

# Cache for API responses
_cache: dict = {}
_cache_ttl = timedelta(minutes=30)


@dataclass
class SeriesData:
    """Standardized data structure for any economic series."""

    id: str
    name: str
    dates: list[str]
    values: list[float]
    source: str  # "fred", "dbnomics", "polymarket"

    # Optional metadata
    units: str = ""
    frequency: str = ""
    title: str = ""
    notes: str = ""
    error: str = ""

    # Comparison metadata
    measure_type: str = ""  # "real", "nominal", "rate", "index"
    change_type: str = ""  # "yoy", "qoq", "mom", "level"

    @property
    def is_empty(self) -> bool:
        return len(self.dates) == 0 or len(self.values) == 0

    @property
    def latest_date(self) -> Optional[str]:
        return self.dates[-1] if self.dates else None

    @property
    def latest_value(self) -> Optional[float]:
        return self.values[-1] if self.values else None


def _get_cached(key: str) -> Optional[dict]:
    """Get cached result if still valid."""
    if key in _cache:
        data, timestamp = _cache[key]
        if datetime.now() - timestamp < _cache_ttl:
            return data
    return None


def _set_cache(key: str, data: dict) -> None:
    """Cache result with timestamp."""
    _cache[key] = (data, datetime.now())


def _fetch_fred(series_id: str, years: int = None) -> SeriesData:
    """
    Fetch data from FRED API.

    Args:
        series_id: FRED series ID (e.g., "UNRATE", "GDPC1")
        years: Optional limit to last N years of data

    Returns:
        SeriesData with observations
    """
    if not FRED_API_KEY:
        return SeriesData(
            id=series_id,
            name=series_id,
            dates=[],
            values=[],
            source="fred",
            error="FRED_API_KEY not set",
        )

    # Build cache key
    start_date = None
    if years:
        start_date = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
    cache_key = f"fred_{series_id}_{start_date}"

    # Check cache
    cached = _get_cached(cache_key)
    if cached and "observations" in cached:
        return _parse_fred_response(series_id, cached)

    # Fetch series info
    info_url = f"{FRED_API_BASE}/series?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
    try:
        req = Request(info_url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            info_data = json.loads(resp.read())
    except Exception as e:
        info_data = {}

    # Fetch observations
    obs_url = f"{FRED_API_BASE}/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
    if start_date:
        obs_url += f"&observation_start={start_date}"

    try:
        req = Request(obs_url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            obs_data = json.loads(resp.read())

        # Merge info and observations for caching
        obs_data["series_info"] = info_data.get("seriess", [{}])[0] if info_data else {}
        _set_cache(cache_key, obs_data)

        return _parse_fred_response(series_id, obs_data)

    except HTTPError as e:
        return SeriesData(
            id=series_id,
            name=series_id,
            dates=[],
            values=[],
            source="fred",
            error=f"FRED API error: {e.code}",
        )
    except Exception as e:
        return SeriesData(
            id=series_id,
            name=series_id,
            dates=[],
            values=[],
            source="fred",
            error=str(e),
        )


def _parse_fred_response(series_id: str, data: dict) -> SeriesData:
    """Parse FRED API response into SeriesData."""
    observations = data.get("observations", [])
    series_info = data.get("series_info", {})

    dates = []
    values = []
    for obs in observations:
        try:
            val = float(obs["value"])
            dates.append(obs["date"])
            values.append(val)
        except (ValueError, KeyError):
            continue

    # Get metadata from catalog if available
    meta = get_series_metadata(series_id)

    return SeriesData(
        id=series_id,
        name=meta.name if meta else series_info.get("title", series_id),
        dates=dates,
        values=values,
        source="fred",
        units=series_info.get("units", ""),
        frequency=series_info.get("frequency", ""),
        title=series_info.get("title", ""),
        notes=series_info.get("notes", "")[:500] if series_info.get("notes") else "",
        measure_type=meta.measure_type if meta else "",
        change_type=meta.change_type if meta else "",
    )


def _fetch_dbnomics(series_key: str, dbnomics_id: str = None) -> SeriesData:
    """
    Fetch data from DBnomics API.

    Args:
        series_key: Our internal key (e.g., "eurozone_gdp")
        dbnomics_id: Full DBnomics ID (e.g., "Eurostat/namq_10_gdp/Q.CLV_PCH_SM.SCA.B1GQ.EA20")

    Returns:
        SeriesData with observations
    """
    # Get metadata from catalog
    meta = get_series_metadata(series_key)
    if not meta and not dbnomics_id:
        return SeriesData(
            id=series_key,
            name=series_key,
            dates=[],
            values=[],
            source="dbnomics",
            error=f"Series {series_key} not found in catalog",
        )

    actual_id = dbnomics_id or (meta.dbnomics_id if meta else None)
    if not actual_id:
        return SeriesData(
            id=series_key,
            name=series_key,
            dates=[],
            values=[],
            source="dbnomics",
            error="No DBnomics ID available",
        )

    cache_key = f"dbnomics_{series_key}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        url = f"{DBNOMICS_API}/series/{actual_id}?observations=1"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        docs = data.get("series", {}).get("docs", [])
        if not docs:
            return SeriesData(
                id=series_key,
                name=meta.name if meta else series_key,
                dates=[],
                values=[],
                source="dbnomics",
                error="No data returned from DBnomics",
            )

        series_data = docs[0]
        periods = series_data.get("period", [])
        raw_values = series_data.get("value", [])

        # Filter out None values and convert periods to dates
        dates = []
        values = []
        for p, v in zip(periods, raw_values):
            if v is not None:
                # Convert period to FRED-style date
                if "Q" in str(p):
                    # Quarterly: 2024-Q1 -> 2024-03-01
                    year, q = str(p).split("-Q")
                    month = {"1": "03", "2": "06", "3": "09", "4": "12"}[q]
                    dates.append(f"{year}-{month}-01")
                elif len(str(p)) == 4:
                    # Annual: 2024 -> 2024-12-31
                    dates.append(f"{p}-12-31")
                elif len(str(p)) == 7:
                    # Monthly: 2024-01 -> 2024-01-01
                    dates.append(f"{p}-01")
                else:
                    dates.append(str(p))
                values.append(float(v))

        result = SeriesData(
            id=series_key,
            name=meta.name if meta else series_data.get("series_name", series_key),
            dates=dates,
            values=values,
            source="dbnomics",
            units=series_data.get("unit", ""),
            frequency=series_data.get("@frequency", meta.frequency if meta else ""),
            measure_type=meta.measure_type if meta else "",
            change_type=meta.change_type if meta else "",
        )

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        return SeriesData(
            id=series_key,
            name=meta.name if meta else series_key,
            dates=[],
            values=[],
            source="dbnomics",
            error=str(e),
        )


class DataFetcher:
    """
    Unified data fetcher that routes to appropriate data source.

    Usage:
        fetcher = DataFetcher()
        data = fetcher.fetch("UNRATE")  # FRED series
        data = fetcher.fetch("eurozone_gdp")  # DBnomics series

        # Fetch multiple in parallel
        results = fetcher.fetch_multiple(["UNRATE", "eurozone_gdp", "GDPC1"])
    """

    def __init__(self, default_years: int = None):
        """
        Initialize fetcher.

        Args:
            default_years: Default years of history to fetch (None = all)
        """
        self.default_years = default_years

    def fetch(self, series_id: str, years: int = None) -> SeriesData:
        """
        Fetch a single series by ID.

        Automatically routes to FRED or DBnomics based on series catalog.

        Args:
            series_id: Series ID (FRED ID or internal DBnomics key)
            years: Optional limit to last N years

        Returns:
            SeriesData with observations
        """
        # Check catalog for source
        meta = get_series_metadata(series_id)

        if meta:
            if meta.source == "dbnomics":
                return _fetch_dbnomics(series_id, meta.dbnomics_id)
            else:
                return _fetch_fred(series_id, years or self.default_years)

        # Not in catalog - assume FRED
        return _fetch_fred(series_id, years or self.default_years)

    def fetch_multiple(
        self, series_ids: list[str], years: int = None, max_workers: int = 5
    ) -> dict[str, SeriesData]:
        """
        Fetch multiple series in parallel.

        Args:
            series_ids: List of series IDs to fetch
            years: Optional limit to last N years
            max_workers: Maximum concurrent fetches

        Returns:
            Dict mapping series_id -> SeriesData
        """
        results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.fetch, sid, years): sid for sid in series_ids
            }

            for future in as_completed(futures):
                series_id = futures[future]
                try:
                    results[series_id] = future.result()
                except Exception as e:
                    results[series_id] = SeriesData(
                        id=series_id,
                        name=series_id,
                        dates=[],
                        values=[],
                        source="unknown",
                        error=str(e),
                    )

        return results


# Convenience functions for backwards compatibility
def get_observations(series_id: str, years: int = None) -> tuple:
    """
    Backwards-compatible interface returning (dates, values, info) tuple.

    This matches the existing app.py interface.
    """
    fetcher = DataFetcher()
    data = fetcher.fetch(series_id, years)

    if data.error:
        return [], [], {"error": data.error}

    info = {
        "id": data.id,
        "name": data.name,
        "title": data.title or data.name,
        "units": data.units,
        "frequency": data.frequency,
        "source": data.source,
        "notes": data.notes,
    }

    return data.dates, data.values, info


# Quick test
if __name__ == "__main__":
    print("Testing Unified Data Fetcher\n" + "=" * 50)

    fetcher = DataFetcher()

    # Test FRED
    print("\n1. FRED Series (UNRATE):")
    data = fetcher.fetch("UNRATE")
    if not data.error:
        print(f"   Name: {data.name}")
        print(f"   Source: {data.source}")
        print(f"   Latest: {data.latest_date} = {data.latest_value}")
    else:
        print(f"   Error: {data.error}")

    # Test DBnomics
    print("\n2. DBnomics Series (eurozone_gdp):")
    data = fetcher.fetch("eurozone_gdp")
    if not data.error:
        print(f"   Name: {data.name}")
        print(f"   Source: {data.source}")
        print(f"   Measure type: {data.measure_type}")
        print(f"   Change type: {data.change_type}")
        print(f"   Latest: {data.latest_date} = {data.latest_value}")
    else:
        print(f"   Error: {data.error}")

    # Test parallel fetch
    print("\n3. Parallel Fetch (UNRATE, GDPC1, eurozone_gdp):")
    results = fetcher.fetch_multiple(["UNRATE", "GDPC1", "eurozone_gdp"])
    for sid, data in results.items():
        if not data.error:
            print(f"   {sid}: {data.latest_value} ({data.latest_date})")
        else:
            print(f"   {sid}: Error - {data.error}")

    # Test backwards-compatible interface
    print("\n4. Backwards Compatible (get_observations):")
    dates, values, info = get_observations("FEDFUNDS")
    if dates:
        print(f"   {info.get('name', 'FEDFUNDS')}")
        print(f"   Latest: {dates[-1]} = {values[-1]}")
    else:
        print(f"   Error: {info.get('error')}")
