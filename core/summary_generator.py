"""
Summary Generator for EconStats.

This module generates analytical (not just descriptive) economic summaries.
The key insight: good economic analysis focuses on the "why" and "what's next",
not just the "what".

Bad summary: "CPI is 2.7%, down from 9% peak"
Good summary: "Inflation has fallen sharply but the last mile to 2% is proving
              difficult. Shelter (4.6%) is the main holdout - it lags rate hikes
              by 18-24 months, so relief should come by mid-2025. Goods are
              deflating (-1.2%), helping offset sticky services."

Key principles:
1. Lead with the insight, not the number
2. Explain causation and lags (Fed policy takes 12-18 months to hit inflation)
3. Note conflicting signals when they exist
4. End with a forward-looking statement
"""

import json
import os
import re
from typing import Optional, Dict, List, Any
from urllib.request import urlopen, Request

# API Keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# =============================================================================
# ECONOMIC FRAMEWORKS
# These capture how economists actually think about causal relationships
# =============================================================================

ECONOMIC_FRAMEWORKS = {
    "inflation": {
        "causal_chain": [
            "Fed raises rates -> mortgages get expensive -> fewer people buy homes -> rent prices eventually fall (takes 18-24 months)",
            "Lots of jobs -> workers get raises -> businesses charge more for services",
            "Supply chains fixed -> stuff (cars, furniture, clothes) gets cheaper",
            "Oil prices jump around -> gas prices swing the headline number",
        ],
        "key_lags": {
            "shelter": "18-24 months after rate hikes. Market rents already fell, but the CPI measure is slow to catch up",
            "wages": "6-12 months after the job market cools off",
            "goods": "Fast - supply chain effects show up quickly",
        },
        "signals_to_watch": [
            "Services prices (excluding rent) - this is what the Fed watches closest",
            "Actual market rents vs what the CPI says - market rents lead by months",
            "Are wages rising faster than workers are producing? That's inflationary",
        ],
        "fed_reaction": "Fed wants 2% inflation. Above 2.5%? They'll keep rates high",
    },
    "labor_market": {
        "causal_chain": [
            "Higher rates -> businesses invest less -> hire fewer people -> job openings drop first",
            "Fewer openings -> workers stop quitting (less confident) -> wage growth slows",
            "If weakness continues -> layoffs start -> unemployment rises (this happens last)",
            "Rule of thumb: If unemployment rises 0.5% from its low, a recession is likely starting",
        ],
        "key_lags": {
            "job_openings": "Early warning sign - drops first when things slow down",
            "quits_rate": "Early warning sign - people stop quitting when nervous",
            "unemployment": "Late signal - rises after everything else has weakened",
            "initial_claims": "Fastest signal - weekly data on new layoffs",
        },
        "signals_to_watch": [
            "Job openings per unemployed person - was 2.0 at peak, now falling",
            "Are people quitting their jobs? Below 2.3% means workers are nervous",
            "Look at 3-month averages - single months are noisy",
        ],
        "current_dynamic": "Job market cooling off from the red-hot 2022-2023 period",
    },
    "recession": {
        "causal_chain": [
            "Long-term rates fall below short-term rates -> banks get cautious about lending -> businesses invest less",
            "People spend less -> companies cut production -> layoffs start",
            "Unemployment rises 0.5% from its low -> recession likely starting",
        ],
        "key_signals": {
            "yield_curve": "When long-term rates fall below short-term rates, recession often follows in 12-18 months",
            "sahm_rule": "Unemployment rising 0.5% from its recent low = recession warning",
            "leading_indicators": "If the leading index falls for 6+ months, watch out",
            "consumer_sentiment": "When confidence crashes, spending usually follows",
        },
        "conflicting_signals": [
            "Yield curve inverted (bad sign) but job market still strong (good sign)",
            "People say they feel bad about the economy but keep spending anyway",
            "Factories are struggling but services are doing fine",
        ],
    },
    "fed_policy": {
        "causal_chain": [
            "Inflation too high -> Fed raises rates -> borrowing gets expensive everywhere",
            "Job market weakens -> wage growth slows -> price increases slow down",
            "Inflation gets close to 2% -> Fed stops raising, then starts cutting -> economy picks up",
        ],
        "reaction_function": {
            "hiking": "Inflation above 2.5% and unemployment below 4.5%? Fed keeps rates high",
            "cutting": "Inflation falling toward 2%, unemployment rising? Fed starts cutting",
            "neutral_rate": "Normal rate is around 2.5-3%. Above that = Fed is trying to slow things down",
        },
        "market_expectations": "You can see what Wall Street expects by looking at futures markets",
        "dot_plot": "Each Fed official shows where they think rates are going - but the market often disagrees",
    },
    "housing": {
        "causal_chain": [
            "Fed raises rates -> mortgage rates spike -> most people can't afford to buy",
            "Homeowners with cheap 3% mortgages won't sell -> not enough homes for sale -> prices stay high",
            "High prices eventually bring more construction -> more supply -> prices ease (eventually)",
        ],
        "key_dynamics": {
            "lock_in_effect": "If you have a 3% mortgage, why would you sell and get a 7% one?",
            "affordability": "Monthly payments relative to income are the worst in decades",
            "rent_vs_buy": "Renting is often cheaper than buying right now (that's unusual)",
        },
    },
    "gdp_growth": {
        "causal_chain": [
            "Consumer spending is 70% of GDP - when people spend, the economy grows",
            "Businesses invest when they expect demand and rates aren't too high",
            "Government spending adds to growth",
            "Trade: We usually import more than we export, which drags on GDP a bit",
        ],
        "key_dynamics": {
            "consumer": "People spend based on: jobs, how wealthy they feel, savings they can tap",
            "business_investment": "Depends on interest rates and profit expectations",
            "inventories": "Jumps around quarter to quarter but tends to even out",
        },
        "trend_growth": "The US economy normally grows about 2% per year. Above that = strong, below = weak",
    },
}


# =============================================================================
# QUERY-SPECIFIC PROMPT TEMPLATES
# Different topics need different analytical focus
# =============================================================================

TOPIC_PROMPTS = {
    "inflation": """Focus on:
- WHAT'S DRIVING IT: Is it goods, services, or rent? Each tells a different story
- RENT LAG: The government's rent measure is 12-18 months behind actual market rents
- GOODS PRICES: Are they falling? That helps offset sticky service prices
- FED REACTION: What does this mean for interest rates?
- WHAT'S NEXT: When does inflation get back to 2%? What could go wrong?

Main point: Getting from 3% to 2% inflation is harder than getting from 9% to 3%. Explain why.""",

    "jobs": """Focus on:
- EARLY vs LATE SIGNALS: Job openings and quits drop first. Unemployment rises last.
- COOLING vs CRASHING: Is this a healthy slowdown from the 2022 frenzy, or something worse?
- WAGES: Are raises feeding into higher prices?
- WHAT'S NEXT: What does this mean for Fed rate cuts? Can we avoid a recession?

Main point: Different job market numbers tell different stories - explain which ones matter most.""",

    "recession": """Focus on:
- MIXED SIGNALS: Some things say recession (yield curve), others say no (jobs, spending)
- HISTORY: How does this compare to past pre-recession periods?
- THE 0.5% RULE: Has unemployment risen half a percent from its low? That's the warning sign
- ODDS: What's the probability of recession in the next year?
- WHAT'S NEXT: What would push us toward or away from recession?

Main point: The signals are mixed - explain both sides.""",

    "fed": """Focus on:
- WHAT WILL THEY DO: Given inflation and jobs, what's the Fed's next move?
- FED vs MARKET: Where does the Fed think rates are going vs what Wall Street thinks?
- HOW FAR: How high will rates go? When can they start cutting?
- WHAT'S NEXT: What data would change their plans?

Main point: The Fed says they're "data-dependent" - explain which data matters most.""",

    "housing": """Focus on:
- CAN PEOPLE AFFORD IT: How do mortgage rates + home prices affect monthly payments?
- WHY NO ONE IS SELLING: People with 3% mortgages won't sell to get a 7% one
- RENT vs BUY: Which makes more financial sense right now?
- NEW HOMES: Is enough construction happening to bring prices down?
- WHAT'S NEXT: What would make housing affordable again?

Main point: The housing market is stuck because no one wants to give up their cheap mortgage.""",

    "gdp": """Focus on:
- WHAT'S DRIVING IT: Consumer spending, business investment, government, trade
- WILL IT LAST: Is this real strength or a one-time bump?
- HOT OR COLD: Is the economy running above or below its normal 2% pace?
- WHAT'S NEXT: What does this mean for the next few quarters?

Main point: GDP tells us where we've been - explain what it means for where we're going.""",
}


# Base prompt template that works for any topic
SUMMARY_PROMPT_TEMPLATE = """You explain economic data in plain English. Your job is to tell people
not just WHAT the numbers say, but WHY it's happening and WHAT IT MEANS for them.

USER QUESTION: {query}

=== GROUND TRUTH (you MUST use these exact numbers) ===
{ground_truth}
=== END GROUND TRUTH ===

FULL DATA:
{data_json}

{topic_guidance}

{framework_context}

{news_context}

Write 2-3 sentences that are ANALYTICAL, not descriptive.

CRITICAL RULES:
- You MUST cite ONLY the numbers from GROUND TRUTH above. Do NOT use any numbers from your training data.
- If GROUND TRUTH says the current rate is 4.1%, you write 4.1%. Never substitute a different number.

FORMAT RULES:
1. LEAD WITH THE INSIGHT, not the number
   BAD: "CPI rose to 2.7% in December"
   GOOD: "Inflation's last mile to 2% is proving sticky as shelter costs remain elevated"

2. EXPLAIN CAUSATION, not just correlation
   BAD: "Unemployment rose as hiring slowed"
   GOOD: "Employers are pulling back on hiring as higher rates dampen demand, pushing unemployment up"

3. NOTE CONFLICTING SIGNALS when they exist
   BAD: "The economy is slowing"
   GOOD: "Job openings are falling but hiring remains solid - a soft landing signature"

4. END WITH FORWARD-LOOKING STATEMENT
   BAD: "The Fed will monitor incoming data"
   GOOD: "If shelter inflation keeps falling at this pace, the Fed can cut rates by June"

5. BE SPECIFIC with numbers and dates — use ONLY GROUND TRUTH numbers
   BAD: "Inflation is coming down"
   GOOD: "Core PCE has fallen from 5.5% to 2.8% - another 0.8pp to reach the Fed's 2% target"

WRITE YOUR 2-3 SENTENCE ANALYTICAL SUMMARY NOW:"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def detect_topic(query: str, series_data: List[Dict]) -> str:
    """Detect the primary topic of a query for specialized prompts."""
    query_lower = query.lower()

    # Check for multi-word phrases FIRST (more specific matches)
    phrase_topics = {
        "housing": ["home price", "house price", "housing price", "real estate",
                    "mortgage rate", "housing market", "home value"],
        "inflation": ["food price", "gas price", "energy price", "price level"],
    }

    for topic, phrases in phrase_topics.items():
        if any(phrase in query_lower for phrase in phrases):
            return topic

    # Check query keywords (ordered by specificity - housing before inflation due to 'prices')
    topic_keywords = {
        "recession": ["recession", "slowdown", "downturn", "contraction", "soft landing"],
        "fed": ["fed", "federal reserve", "monetary policy", "fomc", "powell",
                "dot plot", "rate cut", "rate hike"],
        "housing": ["housing", "home", "mortgage", "real estate"],
        "jobs": ["job", "employment", "unemployment", "payroll", "hiring", "labor", "workers",
                 "layoff", "claims", "wage", "earnings"],
        "gdp": ["gdp", "growth", "output", "economy", "economic growth"],
        "inflation": ["inflation", "cpi", "pce", "prices", "deflation", "shelter", "rent"],
    }

    for topic, keywords in topic_keywords.items():
        if any(kw in query_lower for kw in keywords):
            return topic

    # Check series names as fallback
    if series_data:
        series_names = " ".join([s.get("name", "").lower() for s in series_data])
        for topic, keywords in topic_keywords.items():
            if any(kw in series_names for kw in keywords):
                return topic

    return "general"


def build_framework_context(topic: str) -> str:
    """Build context from economic frameworks for the given topic."""
    # Map topic names to framework names (they differ for some)
    topic_to_framework = {
        "jobs": "labor_market",
        "fed": "fed_policy",
        "gdp": "gdp_growth",
    }
    framework_key = topic_to_framework.get(topic, topic)

    if framework_key not in ECONOMIC_FRAMEWORKS:
        return ""

    framework = ECONOMIC_FRAMEWORKS[framework_key]
    context_parts = []

    if "causal_chain" in framework:
        context_parts.append("CAUSAL RELATIONSHIPS:")
        for chain in framework["causal_chain"]:
            context_parts.append(f"  - {chain}")

    if "key_lags" in framework:
        context_parts.append("\nKEY LAGS TO CONSIDER:")
        for indicator, lag in framework["key_lags"].items():
            context_parts.append(f"  - {indicator}: {lag}")

    if "signals_to_watch" in framework:
        context_parts.append("\nSIGNALS TO WATCH:")
        for signal in framework["signals_to_watch"]:
            context_parts.append(f"  - {signal}")

    return "\n".join(context_parts)


def format_series_data_for_prompt(series_data: List[Dict]) -> str:
    """Format series data for the prompt in a clean JSON format."""
    # Clean up the data for the prompt
    cleaned = []
    for s in series_data:
        item = {
            "name": s.get("name", s.get("series_id", "Unknown")),
            "latest_value": s.get("latest_value"),
            "latest_date": s.get("latest_date"),
        }
        if s.get("yoy_change") is not None:
            item["yoy_change"] = s["yoy_change"]
        if s.get("monthly_job_change") is not None:
            item["monthly_job_change"] = s["monthly_job_change"]
        if s.get("avg_monthly_change_3mo") is not None:
            item["avg_3mo"] = s["avg_monthly_change_3mo"]
        cleaned.append(item)

    return json.dumps(cleaned, indent=2)


def _build_ground_truth_from_dicts(series_data: List[Dict]) -> str:
    """
    Build a GROUND TRUTH block from dict-format series data.

    This prevents the LLM from hallucinating numbers from training data.
    Instead of burying values in the data JSON, we state them prominently
    in a format the LLM can't miss.

    Args:
        series_data: List of dicts with name, latest_value, latest_date,
                     yoy_change, unit, etc.

    Returns:
        Multi-line ground truth string with current values for each series.
    """
    lines = []

    for s in series_data:
        name = s.get("name", s.get("series_id", "Unknown"))
        latest = s.get("latest_value")
        date = s.get("latest_date", "")
        unit = s.get("unit", s.get("units", ""))

        if latest is None:
            continue

        lines.append(f"--- {name} ---")

        # Format based on what data is available
        if s.get("yoy_change") is not None:
            yoy = s["yoy_change"]
            if isinstance(latest, (int, float)):
                lines.append(f"  CURRENT VALUE: {latest} {unit} (as of {date})")
            else:
                lines.append(f"  CURRENT VALUE: {latest} (as of {date})")
            direction = "up" if yoy > 0 else "down" if yoy < 0 else "unchanged"
            lines.append(f"  YEAR-OVER-YEAR: {direction} {abs(yoy)}")
        elif s.get("monthly_job_change") is not None:
            lines.append(f"  LATEST MONTHLY CHANGE: {s['monthly_job_change']:+,} (as of {date})")
            if s.get("avg_monthly_change_3mo") is not None:
                lines.append(f"  3-MONTH AVERAGE: {s['avg_monthly_change_3mo']:+,.0f}")
        elif isinstance(latest, (int, float)):
            lines.append(f"  CURRENT VALUE: {latest} {unit} (as of {date})")
        else:
            lines.append(f"  CURRENT VALUE: {latest} (as of {date})")

    if lines:
        lines.append("")
        lines.append("DO NOT cite any numbers from your training data. Use ONLY the values above.")

    return "\n".join(lines) if lines else ""


# =============================================================================
# MAIN SUMMARY GENERATION FUNCTION
# =============================================================================

def generate_analytical_summary(
    query: str,
    data: List[Dict],
    context: Optional[Dict] = None
) -> str:
    """Generate an analytical (not just descriptive) economic summary.

    This function produces summaries that focus on causation, conflicting signals,
    and forward-looking implications rather than just stating what the data shows.

    Args:
        query: The user's original question
        data: List of dicts with series data. Each dict should have:
            - name: Series name
            - latest_value: Most recent value
            - latest_date: Date of latest value
            - yoy_change: (optional) Year-over-year change
            - unit: (optional) Unit of measurement
        context: Optional dict with additional context:
            - news_context: Recent news/events to incorporate
            - frameworks: Pre-built framework context to use
            - causal_chains: Specific causal chains to reference

    Returns:
        2-3 sentence analytical summary string

    Example:
        >>> data = [{"name": "CPI", "latest_value": 2.7, "yoy_change": -0.2}]
        >>> generate_analytical_summary("What's happening with inflation?", data)
        "Inflation has fallen sharply but the last mile to 2% is proving difficult..."
    """
    if not ANTHROPIC_API_KEY or not data:
        return ""

    context = context or {}

    # Detect topic for specialized prompt
    topic = detect_topic(query, data)

    # Build topic-specific guidance
    topic_guidance = TOPIC_PROMPTS.get(topic, "")
    if topic_guidance:
        topic_guidance = f"ANALYTICAL FOCUS:\n{topic_guidance}"

    # Build framework context
    framework_context = context.get("frameworks", "") or build_framework_context(topic)
    if framework_context:
        framework_context = f"ECONOMIC FRAMEWORK:\n{framework_context}"

    # News context
    news_context = context.get("news_context", "")
    if news_context:
        news_context = f"RECENT NEWS/CONTEXT:\n{news_context}"

    # Format data
    data_json = format_series_data_for_prompt(data)

    # Build GROUND TRUTH block — exact current values the LLM must cite
    ground_truth = _build_ground_truth_from_dicts(data)

    # Build the prompt
    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        query=query,
        data_json=data_json,
        ground_truth=ground_truth,
        topic_guidance=topic_guidance,
        framework_context=framework_context,
        news_context=news_context,
    )

    # Call Claude API
    url = 'https://api.anthropic.com/v1/messages'
    payload = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 400,  # Keep summaries concise
        'messages': [{'role': 'user', 'content': prompt}]
    }
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01'
    }

    try:
        req = Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode('utf-8'))
            summary = result['content'][0]['text'].strip()
            # Clean up any markdown or quotes
            summary = summary.strip('"\'')
            return summary
    except Exception as e:
        print(f"[SummaryGenerator] Error: {e}")
        return ""


# =============================================================================
# CONVENIENCE FUNCTIONS FOR SPECIFIC TOPICS
# =============================================================================

def generate_inflation_summary(data: List[Dict], news_context: str = "") -> str:
    """Generate inflation-focused analytical summary."""
    return generate_analytical_summary(
        query="What's happening with inflation?",
        data=data,
        context={
            "news_context": news_context,
            "frameworks": build_framework_context("inflation"),
        }
    )


def generate_jobs_summary(data: List[Dict], news_context: str = "") -> str:
    """Generate labor market-focused analytical summary."""
    return generate_analytical_summary(
        query="How is the labor market doing?",
        data=data,
        context={
            "news_context": news_context,
            "frameworks": build_framework_context("labor_market"),
        }
    )


def generate_recession_summary(data: List[Dict], news_context: str = "") -> str:
    """Generate recession risk-focused analytical summary."""
    return generate_analytical_summary(
        query="What is the recession risk?",
        data=data,
        context={
            "news_context": news_context,
            "frameworks": build_framework_context("recession"),
        }
    )


def generate_fed_summary(data: List[Dict], news_context: str = "") -> str:
    """Generate Fed policy-focused analytical summary."""
    return generate_analytical_summary(
        query="What will the Fed do?",
        data=data,
        context={
            "news_context": news_context,
            "frameworks": build_framework_context("fed_policy"),
        }
    )


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def _test_with_sample_data():
    """Test the summary generator with sample data."""

    # Sample inflation data
    inflation_data = [
        {
            "name": "Consumer Price Index (CPI)",
            "series_id": "CPIAUCSL",
            "latest_value": 2.7,
            "latest_date": "2024-12-01",
            "yoy_change": -0.2,
            "recent_5yr_min": 0.1,
            "recent_5yr_max": 9.1,
        },
        {
            "name": "Core CPI (ex food and energy)",
            "series_id": "CPILFESL",
            "latest_value": 3.2,
            "latest_date": "2024-12-01",
            "yoy_change": -0.1,
        },
        {
            "name": "Shelter CPI",
            "series_id": "CUSR0000SAH1",
            "latest_value": 4.6,
            "latest_date": "2024-12-01",
            "yoy_change": -0.8,
        },
    ]

    print("=" * 60)
    print("INFLATION SUMMARY TEST")
    print("=" * 60)
    print("\nInput data:")
    print(json.dumps(inflation_data, indent=2))
    print("\nGenerating summary...")

    summary = generate_analytical_summary(
        query="What's happening with inflation?",
        data=inflation_data,
    )
    print(f"\nSummary:\n{summary}")

    # Sample jobs data
    jobs_data = [
        {
            "name": "Unemployment Rate",
            "series_id": "UNRATE",
            "latest_value": 4.1,
            "latest_date": "2024-12-01",
            "yoy_change": 0.4,
        },
        {
            "name": "Total Nonfarm Payrolls",
            "series_id": "PAYEMS",
            "latest_value": 159000,
            "latest_date": "2024-12-01",
            "monthly_job_change": 227,
            "avg_monthly_change_3mo": 180,
            "avg_monthly_change_12mo": 186,
        },
        {
            "name": "Job Openings",
            "series_id": "JTSJOL",
            "latest_value": 8800,
            "latest_date": "2024-11-01",
            "yoy_change": -900,
        },
    ]

    print("\n" + "=" * 60)
    print("JOBS SUMMARY TEST")
    print("=" * 60)
    print("\nInput data:")
    print(json.dumps(jobs_data, indent=2))
    print("\nGenerating summary...")

    summary = generate_analytical_summary(
        query="How is the job market doing?",
        data=jobs_data,
    )
    print(f"\nSummary:\n{summary}")


if __name__ == "__main__":
    _test_with_sample_data()
