"""
Unified Cache Manager - Three Tiers

Tier 1: Routing cache (1 hour TTL)
  - Query -> RoutingResult (series IDs, show_yoy, etc.)
  - Most queries hit this cache

Tier 2: Data cache (30 min TTL)
  - Series ID -> raw data (dates, values)
  - Reduces API calls to FRED/etc.

Tier 3: LLM response cache (1 hour TTL)
  - Query + data hash -> AI summary
  - Avoids regenerating summaries for same data
"""

import hashlib
import time
import random
import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from collections import OrderedDict

from config import config


@dataclass
class CacheEntry:
    """Single cache entry with value and expiration."""
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)
    ttl: float = 0  # Original TTL for stampede protection


class LRUCache:
    """
    LRU cache with TTL support and stampede protection.

    Uses probabilistic early expiration (XFetch algorithm) to prevent
    cache stampedes when popular entries expire simultaneously.
    """

    def __init__(self, max_size: int = 10000, stampede_beta: float = 1.0):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of entries
            stampede_beta: Stampede protection factor (higher = earlier recompute)
                          Set to 0 to disable stampede protection
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._stampede_beta = stampede_beta

    def get(self, key: str, stampede_protection: bool = True) -> Optional[Any]:
        """
        Get value if exists and not expired.

        Uses XFetch algorithm for stampede protection:
        - As entry approaches expiration, probability of returning None increases
        - This allows one request to regenerate cache while others still get cached value

        Args:
            key: Cache key
            stampede_protection: If True, use probabilistic early expiration
        """
        if key not in self._cache:
            return None

        entry = self._cache[key]
        now = time.time()

        # Check hard expiration
        if now > entry.expires_at:
            del self._cache[key]
            return None

        # Stampede protection: probabilistic early expiration
        if stampede_protection and self._stampede_beta > 0 and entry.ttl > 0:
            time_remaining = entry.expires_at - now
            # XFetch algorithm: return None with probability that increases as expiration approaches
            # Using -log(random) gives exponential distribution, beta controls aggressiveness
            threshold = self._stampede_beta * entry.ttl * 0.1  # 10% of TTL window
            if time_remaining < threshold * (-math.log(random.random() + 0.001)):
                # Early expiration triggered - one request will regenerate
                return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return entry.value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value with TTL in seconds."""
        # Evict oldest if at capacity
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = CacheEntry(
            value=value,
            expires_at=time.time() + ttl,
            ttl=ttl
        )

    def delete(self, key: str) -> bool:
        """Delete key if exists."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()

    def stats(self) -> dict:
        """Get cache statistics."""
        now = time.time()
        valid = sum(1 for e in self._cache.values() if e.expires_at > now)
        return {
            'total_entries': len(self._cache),
            'valid_entries': valid,
            'expired_entries': len(self._cache) - valid,
            'max_size': self._max_size,
        }


class CacheManager:
    """
    Three-tier cache manager for EconStats.

    Tiers:
    1. Routing: query -> plan (1 hour)
    2. Data: series_id -> (dates, values) (30 min)
    3. Summary: query+data_hash -> AI summary (1 hour)
    4. Bullets: series_id -> bullet list (24 hours)
    """

    def __init__(self):
        self._routing = LRUCache(max_size=10000)
        self._data = LRUCache(max_size=5000)
        self._summary = LRUCache(max_size=5000)
        self._bullets = LRUCache(max_size=2000)

    # =========================================================================
    # Tier 1: Routing Cache
    # =========================================================================

    def get_routing(self, query: str) -> Optional[dict]:
        """Get cached routing result for a query."""
        key = self._routing_key(query)
        return self._routing.get(key)

    def set_routing(self, query: str, plan: dict) -> None:
        """Cache routing result for a query."""
        key = self._routing_key(query)
        self._routing.set(key, plan, config.routing_cache_ttl)

    def _routing_key(self, query: str) -> str:
        """Generate cache key for routing."""
        normalized = query.lower().strip()
        return f"route:{normalized}"

    # =========================================================================
    # Tier 2: Data Cache
    # =========================================================================

    def get_data(self, series_id: str, years: int) -> Optional[tuple]:
        """Get cached data for a series. Returns (dates, values, info) or None."""
        key = self._data_key(series_id, years)
        return self._data.get(key)

    def set_data(self, series_id: str, years: int, dates: List[str], values: List[float], info: dict) -> None:
        """Cache data for a series."""
        key = self._data_key(series_id, years)
        self._data.set(key, (dates, values, info), config.data_cache_ttl)

    def _data_key(self, series_id: str, years: int) -> str:
        """Generate cache key for data."""
        return f"data:{series_id}:{years}"

    # =========================================================================
    # Tier 3: Summary Cache
    # =========================================================================

    def get_summary(self, query: str, data_hash: str) -> Optional[str]:
        """Get cached AI summary."""
        key = self._summary_key(query, data_hash)
        return self._summary.get(key)

    def set_summary(self, query: str, data_hash: str, summary: str) -> None:
        """Cache AI summary."""
        key = self._summary_key(query, data_hash)
        self._summary.set(key, summary, config.summary_cache_ttl)

    def _summary_key(self, query: str, data_hash: str) -> str:
        """Generate cache key for summary."""
        query_norm = query.lower().strip()
        return f"summary:{query_norm}:{data_hash}"

    @staticmethod
    def hash_data(series_data: List[tuple]) -> str:
        """Generate hash of series data for cache key."""
        # Hash based on series IDs and latest values
        parts = []
        for series_id, dates, values, info in series_data:
            if values:
                parts.append(f"{series_id}:{values[-1]:.2f}")
            else:
                parts.append(f"{series_id}:empty")

        combined = "|".join(sorted(parts))
        return hashlib.md5(combined.encode()).hexdigest()[:12]

    # =========================================================================
    # Tier 4: Bullets Cache
    # =========================================================================

    def get_bullets(self, series_id: str, latest_date: str) -> Optional[List[str]]:
        """Get cached bullets for a series."""
        key = f"bullets:{series_id}:{latest_date}"
        return self._bullets.get(key)

    def set_bullets(self, series_id: str, latest_date: str, bullets: List[str]) -> None:
        """Cache bullets for a series."""
        key = f"bullets:{series_id}:{latest_date}"
        self._bullets.set(key, bullets, config.bullet_cache_ttl)

    # =========================================================================
    # Utilities
    # =========================================================================

    def stats(self) -> dict:
        """Get cache statistics for all tiers."""
        return {
            'routing': self._routing.stats(),
            'data': self._data.stats(),
            'summary': self._summary.stats(),
            'bullets': self._bullets.stats(),
        }

    def clear_all(self) -> None:
        """Clear all caches."""
        self._routing.clear()
        self._data.clear()
        self._summary.clear()
        self._bullets.clear()


# Global cache instance
cache_manager = CacheManager()
