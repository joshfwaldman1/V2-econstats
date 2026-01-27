#!/usr/bin/env python
"""
Benchmark script for pandas analytics layer.

Measures the overhead of computing analytics with pandas.
"""

import time
import sys
import random
from datetime import datetime, timedelta

# Add parent to path
sys.path.insert(0, '/private/tmp/econstats-v2')

from processing.analytics import compute_series_analytics, analytics_to_text


def generate_test_data(n_points: int = 120) -> tuple:
    """Generate realistic economic data for testing."""
    # Generate dates (monthly)
    end_date = datetime.now()
    dates = []
    for i in range(n_points - 1, -1, -1):
        d = end_date - timedelta(days=30 * i)
        dates.append(d.strftime('%Y-%m-%d'))

    # Generate values with realistic trend and noise
    base = 100.0
    values = []
    for i in range(n_points):
        # Upward trend with noise
        trend = i * 0.1
        noise = random.gauss(0, 2)
        values.append(base + trend + noise)

    return dates, values


def benchmark_analytics():
    """Run benchmark and report results."""
    print("=" * 60)
    print("PANDAS ANALYTICS BENCHMARK")
    print("=" * 60)

    # Test with different data sizes
    sizes = [12, 60, 120, 240, 480]  # 1yr, 5yr, 10yr, 20yr, 40yr monthly data
    iterations = 100

    for size in sizes:
        dates, values = generate_test_data(size)

        # Warmup
        for _ in range(10):
            compute_series_analytics(dates, values, 'TEST', 'monthly')

        # Benchmark
        start = time.perf_counter()
        for _ in range(iterations):
            result = compute_series_analytics(dates, values, 'TEST', 'monthly')
        end = time.perf_counter()

        avg_ms = ((end - start) / iterations) * 1000
        print(f"\n{size:3d} points ({size/12:.0f} years): {avg_ms:.3f} ms per call")
        print(f"    Total for {iterations} iterations: {(end - start) * 1000:.1f} ms")

    # Test text conversion
    print("\n" + "-" * 60)
    print("TEXT CONVERSION:")
    dates, values = generate_test_data(120)
    analytics = compute_series_analytics(dates, values, 'TEST', 'monthly')

    start = time.perf_counter()
    for _ in range(iterations):
        text = analytics_to_text(analytics)
    end = time.perf_counter()

    avg_ms = ((end - start) / iterations) * 1000
    print(f"analytics_to_text: {avg_ms:.4f} ms per call")

    # Show sample output
    print("\n" + "-" * 60)
    print("SAMPLE OUTPUT:")
    print(f"Analytics keys: {list(analytics.keys())}")
    print(f"\nText summary:\n{text}")

    # Total overhead estimate
    print("\n" + "=" * 60)
    print("OVERHEAD ESTIMATE:")
    print("=" * 60)
    print("Typical request: 3-5 series, 10 years each")
    dates, values = generate_test_data(120)

    start = time.perf_counter()
    for _ in range(5):  # 5 series
        compute_series_analytics(dates, values, f'SERIES_{_}', 'monthly')
    end = time.perf_counter()

    total_ms = (end - start) * 1000
    print(f"5 series x 10yr: {total_ms:.2f} ms ({total_ms/1000:.4f} seconds)")
    print(f"\nThis is NEGLIGIBLE compared to:")
    print(f"  - Network RTT to FRED: 100-500ms")
    print(f"  - LLM API call: 500-3000ms")


if __name__ == "__main__":
    benchmark_analytics()
