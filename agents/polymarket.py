"""
Polymarket prediction market integration for EconStats.

Fetches economic prediction market data (recession odds, Fed rate expectations, GDP forecasts)
to complement FRED historical data with forward-looking market sentiment.
"""

import requests
from datetime import datetime, timedelta
from typing import Optional
import json

# Cache to avoid excessive API calls
_cache: dict = {}
_cache_ttl = timedelta(minutes=15)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"

# Curated list of economic event slugs to track
# market_type: "binary" = Yes/No (display as "X%"), "multi" = multiple outcomes (skip or handle specially)
# NOTE: Slugs change frequently on Polymarket - update these when markets expire/new ones launch
# Last updated: January 2026
ECONOMIC_EVENTS = {
    # ==========================================================================
    # RECESSION / GDP (ACTIVE)
    # ==========================================================================
    "us-recession-by-end-of-2026": {
        "category": "recession",
        "display_name": "US Recession by End of 2026",
        # Broad keywords to match many economy-related queries
        "keywords": ["recession", "economic downturn", "contraction", "hard landing", "soft landing",
                     "economy", "economic outlook", "how is the economy", "economic conditions"],
        "market_type": "binary",
    },
    "negative-gdp-growth-in-2025": {
        "category": "gdp",
        "display_name": "Negative GDP Growth in 2025",
        "keywords": ["gdp", "growth", "economy", "recession", "contraction", "economic growth"],
        "market_type": "binary",
    },
    "negative-gdp-growth-in-q4-2025-295": {
        "category": "gdp",
        "display_name": "Negative GDP Growth in Q4 2025",
        "keywords": ["gdp", "growth", "q4", "fourth quarter", "economy"],
        "market_type": "binary",
    },
    "gdp-growth-in-2025": {
        "category": "gdp",
        "display_name": "GDP Growth in 2025",
        "keywords": ["gdp", "growth", "economy", "expansion"],
        "market_type": "multi",  # Multiple buckets like 0-1%, 1-2%, etc.
    },
    "us-gdp-growth-in-q4-2025": {
        "category": "gdp",
        "display_name": "US GDP Growth in Q4 2025",
        "keywords": ["gdp", "growth", "q4", "fourth quarter"],
        "market_type": "multi",
    },

    # ==========================================================================
    # FEDERAL RESERVE / INTEREST RATES (ACTIVE)
    # ==========================================================================
    "fed-decision-in-january": {
        "category": "fed",
        "display_name": "Fed Rate Cut in January",
        "keywords": ["fed", "federal reserve", "interest rate", "fomc", "rate cut", "powell",
                     "monetary policy", "rates", "rate decision"],
        "market_type": "binary",
    },
    "fed-decision-in-march-885": {
        "category": "fed",
        "display_name": "Fed Rate Cut in March",
        "keywords": ["fed", "federal reserve", "interest rate", "fomc", "rate cut", "powell", "rates"],
        "market_type": "binary",
    },
    "how-many-fed-rate-cuts-in-2026": {
        "category": "fed",
        "display_name": "Fed Rate Cuts in 2026",
        "keywords": ["fed", "rate cut", "monetary policy", "fomc", "easing", "rates"],
        "market_type": "multi",
    },
    "next-three-fed-decisions": {
        "category": "fed",
        "display_name": "Fed Decisions (Oct-Jan)",
        "keywords": ["fed", "fomc", "rate decision", "federal reserve"],
        "market_type": "multi",
    },
    "next-three-fed-decisions-847": {
        "category": "fed",
        "display_name": "Fed Decisions (Dec-Mar)",
        "keywords": ["fed", "fomc", "rate decision", "federal reserve"],
        "market_type": "multi",
    },
    "who-will-trump-nominate-as-fed-chair": {
        "category": "fed",
        "display_name": "Trump Fed Chair Nominee",
        "keywords": ["fed", "fed chair", "powell", "federal reserve", "trump"],
        "market_type": "multi",
    },
    "lisa-cook-out-as-fed-governor-by-september-30": {
        "category": "fed",
        "display_name": "Lisa Cook Out as Fed Governor",
        "keywords": ["fed", "fed governor", "federal reserve"],
        "market_type": "binary",
    },

    # ==========================================================================
    # TRADE / TARIFFS (ACTIVE)
    # ==========================================================================
    "will-tariffs-generate-250b-in-2025": {
        "category": "tariffs",
        "display_name": "Tariffs >$250B in 2025",
        "keywords": ["tariffs", "trade", "trade war", "china", "imports", "protectionism", "trump tariffs"],
        "market_type": "binary",
    },
    "how-much-revenue-will-the-us-raise-from-tariffs-in-2025": {
        "category": "tariffs",
        "display_name": "US Tariff Revenue in 2025",
        "keywords": ["tariffs", "trade", "revenue", "imports"],
        "market_type": "multi",
    },
    "will-the-supreme-court-rule-in-favor-of-trumps-tariffs": {
        "category": "tariffs",
        "display_name": "Supreme Court Rules for Trump Tariffs",
        "keywords": ["tariffs", "supreme court", "trade", "trump"],
        "market_type": "binary",
    },

    # ==========================================================================
    # LABOR MARKET / UNEMPLOYMENT (ACTIVE)
    # ==========================================================================
    # NOTE: Brazil unemployment removed - not relevant for US-focused queries
    # Only add US unemployment markets here when they become available

    # ==========================================================================
    # CRYPTO (ACTIVE - often market sentiment indicator)
    # ==========================================================================
    "will-bitcoin-hit-80k-or-150k-first": {
        "category": "crypto",
        "display_name": "Bitcoin: $80K or $150K First?",
        "keywords": ["bitcoin", "crypto", "cryptocurrency", "btc"],
        "market_type": "binary",
    },
    "when-will-bitcoin-hit-150k": {
        "category": "crypto",
        "display_name": "When Will Bitcoin Hit $150K",
        "keywords": ["bitcoin", "crypto", "cryptocurrency", "btc"],
        "market_type": "multi",
    },
    "another-sp-500-company-buys-bitcoin-by-november-30": {
        "category": "crypto",
        "display_name": "S&P 500 Company Buys Bitcoin",
        "keywords": ["bitcoin", "crypto", "s&p 500", "corporate", "btc"],
        "market_type": "binary",
    },
    "microstrategy-sell-any-bitcoin-in-2025": {
        "category": "crypto",
        "display_name": "MicroStrategy Sells Bitcoin in 2025",
        "keywords": ["bitcoin", "microstrategy", "crypto", "btc"],
        "market_type": "binary",
    },
    "trump-eliminates-capital-gains-tax-on-crypto-in-2025": {
        "category": "crypto",
        "display_name": "Trump Eliminates Crypto Capital Gains Tax",
        "keywords": ["crypto", "bitcoin", "tax", "capital gains", "trump"],
        "market_type": "binary",
    },
    "another-crypto-hack-over-100m-in-2025": {
        "category": "crypto",
        "display_name": "Another >$100M Crypto Hack in 2025",
        "keywords": ["crypto", "hack", "security", "bitcoin"],
        "market_type": "binary",
    },
}


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


def fetch_event(slug: str) -> Optional[dict]:
    """
    Fetch a single event by slug from Polymarket.

    Returns event data with markets, or None on error.
    """
    cache_key = f"event_{slug}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        # Get events list and find by slug
        resp = requests.get(
            f"{GAMMA_API_BASE}/events",
            params={"closed": "false", "limit": 500},
            timeout=10
        )
        resp.raise_for_status()
        events = resp.json()

        for event in events:
            if event.get("slug") == slug:
                _set_cache(cache_key, event)
                return event

        return None
    except Exception as e:
        print(f"[Polymarket] Error fetching event {slug}: {e}")
        return None


def fetch_all_economic_events() -> list[dict]:
    """
    Fetch all tracked economic events from Polymarket.

    Returns list of event data with parsed probabilities.
    """
    cache_key = "all_economic_events"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    results = []

    try:
        # Fetch all events in one call
        resp = requests.get(
            f"{GAMMA_API_BASE}/events",
            params={"closed": "false", "limit": 500},
            timeout=10
        )
        resp.raise_for_status()
        all_events = resp.json()

        # Index by slug
        events_by_slug = {e.get("slug"): e for e in all_events}

        # Process tracked events
        for slug, meta in ECONOMIC_EVENTS.items():
            event = events_by_slug.get(slug)
            if not event:
                continue

            parsed = parse_event(event, meta)
            if parsed:
                results.append(parsed)

        _set_cache(cache_key, results)
        return results

    except Exception as e:
        print(f"[Polymarket] Error fetching events: {e}")
        return []


def parse_event(event: dict, meta: dict) -> Optional[dict]:
    """
    Parse event data into a standardized format.

    Returns:
        {
            "slug": "us-recession-by-end-of-2026",
            "title": "US Recession by End of 2026",
            "category": "recession",
            "volume": 170265,
            "markets": [
                {"outcome": "Yes", "probability": 0.225},
                {"outcome": "No", "probability": 0.775}
            ],
            "last_updated": "2026-01-23T21:45:05Z"
        }
    """
    try:
        markets = event.get("markets", [])
        if not markets:
            return None

        parsed_markets = []
        for m in markets:
            outcomes = json.loads(m.get("outcomes", "[]"))
            prices = json.loads(m.get("outcomePrices", "[]"))

            if len(outcomes) == len(prices):
                for outcome, price in zip(outcomes, prices):
                    try:
                        prob = float(price)
                        parsed_markets.append({
                            "outcome": outcome,
                            "probability": prob,
                            "question": m.get("question", ""),
                        })
                    except (ValueError, TypeError):
                        continue

        if not parsed_markets:
            return None

        return {
            "slug": event.get("slug"),
            "title": meta.get("display_name", event.get("title")),
            "category": meta.get("category"),
            "keywords": meta.get("keywords", []),
            "market_type": meta.get("market_type", "binary"),
            "volume": event.get("volume", 0),
            "liquidity": event.get("liquidity", 0),
            "markets": parsed_markets,
            "end_date": event.get("endDate"),
            "last_updated": event.get("updatedAt"),
            "url": f"https://polymarket.com/event/{event.get('slug')}",
        }

    except Exception as e:
        print(f"[Polymarket] Error parsing event: {e}")
        return None


def get_recession_odds() -> Optional[dict]:
    """
    Get current recession probability from Polymarket.

    Returns:
        {
            "probability": 0.225,
            "volume": 170265,
            "title": "US Recession by End of 2026",
            "url": "https://polymarket.com/event/..."
        }
    """
    events = fetch_all_economic_events()
    for event in events:
        if event.get("category") == "recession":
            # Find the "Yes" probability
            for market in event.get("markets", []):
                if market.get("outcome") == "Yes":
                    return {
                        "probability": market["probability"],
                        "volume": event.get("volume", 0),
                        "title": event.get("title"),
                        "url": event.get("url"),
                        "end_date": event.get("end_date"),
                    }
    return None


def get_fed_rate_expectations() -> list[dict]:
    """
    Get Fed rate cut expectations from Polymarket.

    Returns list of markets related to Fed decisions.
    """
    events = fetch_all_economic_events()
    fed_events = [e for e in events if e.get("category") == "fed"]
    return fed_events


def get_gdp_expectations() -> list[dict]:
    """
    Get GDP growth expectations from Polymarket.
    """
    events = fetch_all_economic_events()
    gdp_events = [e for e in events if e.get("category") == "gdp"]
    return gdp_events


def find_relevant_predictions(query: str) -> list[dict]:
    """
    Find prediction markets relevant to a user query.

    Args:
        query: User's question (e.g., "will there be a recession?")

    Returns:
        List of relevant prediction market data
    """
    query_lower = query.lower()
    events = fetch_all_economic_events()

    relevant = []
    for event in events:
        # Check if query matches any keywords
        keywords = event.get("keywords", [])
        title = event.get("title", "").lower()

        score = 0
        for kw in keywords:
            if kw in query_lower:
                score += 2

        # Also check title words
        for word in query_lower.split():
            if len(word) > 3 and word in title:
                score += 1

        if score > 0:
            event["relevance_score"] = score
            relevant.append(event)

    # Sort by relevance then volume
    relevant.sort(key=lambda x: (-x.get("relevance_score", 0), -x.get("volume", 0)))
    return relevant


def synthesize_prediction_narrative(predictions: list) -> Optional[str]:
    """
    Synthesize multiple predictions into a coherent narrative paragraph.

    Instead of listing probabilities, describes what the overall picture looks like
    with appropriate caveats about the data source.
    """
    if not predictions:
        return None

    # Extract probabilities by category
    recession_prob = None
    negative_gdp_prob = None
    fed_cut_probs = {}
    tariff_prob = None

    for pred in predictions:
        if pred.get("market_type") == "multi":
            continue

        slug = pred.get("slug", "")
        markets = pred.get("markets", [])

        # Find "Yes" probability
        prob = None
        for m in markets:
            if m.get("outcome") in ("Yes", "1", "True"):
                prob = m.get("probability", 0) * 100
                break

        if prob is None:
            continue

        if "recession" in slug:
            recession_prob = prob
        elif "negative-gdp" in slug:
            negative_gdp_prob = prob
        elif "fed-decision" in slug or "rate-cut" in slug:
            if "january" in slug:
                fed_cut_probs["January"] = prob
            elif "march" in slug:
                fed_cut_probs["March"] = prob
        elif "tariff" in slug and "250b" in slug:
            tariff_prob = prob

    # Build narrative based on what we have
    parts = []

    # Economic outlook narrative
    if recession_prob is not None or negative_gdp_prob is not None:
        if recession_prob is not None and negative_gdp_prob is not None:
            if recession_prob < 25 and negative_gdp_prob < 10:
                parts.append(f"Traders appear relatively optimistic about growth, pricing in only a {negative_gdp_prob:.0f}% chance of GDP contraction in 2025 and {recession_prob:.0f}% odds of recession through 2026.")
            elif recession_prob >= 40:
                parts.append(f"Markets show meaningful concern about a downturn, with recession odds at {recession_prob:.0f}% through 2026 and a {negative_gdp_prob:.0f}% chance of negative GDP growth this year.")
            else:
                parts.append(f"Markets see recession as possible but not the base case ({recession_prob:.0f}% odds through 2026), with only {negative_gdp_prob:.0f}% chance of outright GDP decline in 2025.")
        elif recession_prob is not None:
            if recession_prob < 20:
                parts.append(f"Traders see recession as unlikely, pricing it at just {recession_prob:.0f}% through end of 2026.")
            elif recession_prob < 40:
                parts.append(f"Recession odds sit at {recession_prob:.0f}% through 2026—a real but not dominant risk in traders' view.")
            else:
                parts.append(f"Elevated recession concern: markets put {recession_prob:.0f}% odds on a downturn by end of 2026.")
        elif negative_gdp_prob is not None:
            if negative_gdp_prob < 10:
                parts.append(f"Traders see GDP contraction as very unlikely in 2025, at just {negative_gdp_prob:.0f}%.")
            else:
                parts.append(f"There's a {negative_gdp_prob:.0f}% chance markets assign to negative GDP growth in 2025.")

    # Fed narrative
    if fed_cut_probs:
        months = sorted(fed_cut_probs.keys(), key=lambda x: ["January", "February", "March", "April", "May", "June"].index(x) if x in ["January", "February", "March", "April", "May", "June"] else 99)
        if all(p < 10 for p in fed_cut_probs.values()):
            parts.append(f"The Fed is expected to hold steady near-term, with rate cut odds below 10% for upcoming meetings.")
        elif any(p > 50 for p in fed_cut_probs.values()):
            high_month = [m for m, p in fed_cut_probs.items() if p > 50][0]
            parts.append(f"Markets are pricing in a likely rate cut in {high_month} ({fed_cut_probs[high_month]:.0f}% odds).")
        else:
            probs_str = ", ".join([f"{m}: {p:.0f}%" for m, p in fed_cut_probs.items()])
            parts.append(f"Rate cut odds remain modest ({probs_str}).")

    # Tariff narrative
    if tariff_prob is not None:
        if tariff_prob < 20:
            parts.append(f"Major tariff escalation (>$250B) seen as unlikely at {tariff_prob:.0f}%.")
        else:
            parts.append(f"Traders put {tariff_prob:.0f}% odds on tariffs exceeding $250B in 2025.")

    if not parts:
        return None

    return " ".join(parts)


def format_prediction_for_display(prediction: dict) -> Optional[str]:
    """Format a single prediction - used as fallback."""
    if prediction.get("market_type") == "multi":
        return None

    slug = prediction.get("slug", "")
    markets = prediction.get("markets", [])

    prob = None
    for m in markets:
        if m.get("outcome") in ("Yes", "1", "True"):
            prob = m.get("probability", 0) * 100
            break

    if prob is None:
        return None

    title = prediction.get("title", "")
    return f"{title}: {prob:.0f}%"


def format_predictions_box(predictions: list, query: str = "") -> Optional[str]:
    """
    Format prediction market data as a styled HTML box for display.

    Args:
        predictions: List of prediction dicts from find_relevant_predictions()
        query: Original user query (for context)

    Returns:
        HTML string for display, or None if no relevant predictions
    """
    if not predictions:
        return None

    # Filter to only binary markets with valid probabilities
    display_items = []
    for pred in predictions[:4]:  # Max 4 predictions
        if pred.get("market_type") == "multi":
            continue

        markets = pred.get("markets", [])
        prob = None
        for m in markets:
            if m.get("outcome") in ("Yes", "1", "True"):
                prob = m.get("probability", 0) * 100
                break

        if prob is not None:
            title = pred.get("title", "")
            url = pred.get("url", "")
            category = pred.get("category", "")

            # Color code by probability
            if prob >= 70:
                color = "#059669"  # Green - likely
            elif prob >= 40:
                color = "#d97706"  # Amber - uncertain
            else:
                color = "#6b7280"  # Gray - unlikely

            display_items.append({
                "title": title,
                "prob": prob,
                "url": url,
                "color": color,
                "category": category,
            })

    if not display_items:
        return None

    # Build HTML - using table for better Streamlit compatibility
    # HTML-escape titles to prevent rendering issues with special characters
    import html as html_lib

    # Build items as table rows for better compatibility
    rows_html = ""
    for item in display_items:
        safe_title = html_lib.escape(item["title"])
        rows_html += f'<tr><td style="color: #0f172a; font-size: 0.875rem; font-weight: 500; padding: 0.75rem 0; border-bottom: 1px solid #f1f5f9;">{safe_title}</td><td style="color: {item["color"]}; font-weight: 600; font-size: 0.875rem; text-align: right; padding: 0.75rem 0; border-bottom: 1px solid #f1f5f9;">{item["prob"]:.0f}%</td></tr>'

    # Build complete HTML using string concatenation (not f-string for the items)
    html = (
        '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 1rem; margin: 0 0 1.5rem 0; overflow: hidden; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);">'
        '<div style="padding: 1rem 1.5rem; border-bottom: 1px solid #f1f5f9;">'
        '<div style="display: flex; justify-content: space-between; align-items: center;">'
        '<div><h3 style="font-weight: 600; color: #0f172a; font-size: 1rem; margin: 0;">What Markets Expect</h3>'
        '<p style="color: #64748b; font-size: 0.875rem; margin: 0.25rem 0 0 0;">Prediction market probabilities</p></div>'
        '<span style="font-size: 0.7rem; color: #94a3b8;">via Polymarket</span>'
        '</div></div>'
        '<div style="padding: 0 1.5rem;">'
        '<table style="width: 100%; border-collapse: collapse;">' + rows_html + '</table>'
        '</div>'
        '<div style="padding: 0.75rem 1.5rem; background: #f8fafc; border-top: 1px solid #f1f5f9;">'
        '<p style="font-size: 0.75rem; color: #94a3b8; margin: 0;">Markets reflect trader expectations, not forecasts. Odds can change rapidly.</p>'
        '</div></div>'
    )

    return html


def get_predictions_for_query(query: str) -> tuple[list, Optional[str]]:
    """
    Get relevant predictions and formatted HTML for a query.

    Returns:
        (predictions_list, html_box) - both may be empty/None if no matches
    """
    predictions = find_relevant_predictions(query)
    if not predictions:
        return [], None

    html = format_predictions_box(predictions, query)
    return predictions, html


# Quick test
if __name__ == "__main__":
    print("Testing Polymarket integration...\n")

    # Test recession odds
    recession = get_recession_odds()
    if recession:
        print(f"Recession odds: {recession['probability']*100:.1f}%")
        print(f"  Volume: ${recession['volume']:,.0f}")
        print(f"  Market: {recession['title']}")
        print(f"  URL: {recession['url']}\n")

    # Test Fed expectations
    fed = get_fed_rate_expectations()
    print(f"Found {len(fed)} Fed-related markets:")
    for event in fed[:3]:
        print(f"  - {format_prediction_for_display(event)}")

    print("\n" + "="*50)

    # Test query matching
    test_queries = [
        "will there be a recession?",
        "what will the fed do?",
        "gdp growth outlook",
    ]

    for q in test_queries:
        print(f"\nQuery: '{q}'")
        relevant = find_relevant_predictions(q)
        for r in relevant[:2]:
            print(f"  → {format_prediction_for_display(r)}")
