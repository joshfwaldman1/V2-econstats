"""
Structured prompt templates for economic analysis.

This module provides prompt templates that guide LLMs to think like credible
economists (Jason Furman, Claudia Sahm style) when analyzing economic questions.

The prompts enforce a disciplined analytical framework:
1. Frame the question properly
2. Map the causal chain
3. Provide historical context
4. Acknowledge conflicting signals
5. Look forward with probabilistic thinking

Usage:
    from core.economist_prompt import build_economist_prompt, ANALYSIS_TEMPLATES

    prompt = build_economist_prompt(
        query="Is inflation coming down?",
        data_context={"cpi_yoy": 2.9, "core_pce": 2.7, ...}
    )
"""

from typing import Dict, Any, Optional


# =============================================================================
# CORE ECONOMIST PROMPT TEMPLATE
# =============================================================================

ECONOMIST_PROMPT_TEMPLATE = """You are an economic analyst who explains things clearly.
Your job: help people understand what's happening in the economy and what it means for them.

Be honest about what we know, what we think, and what we're guessing.

## USER QUESTION
{query}

## CURRENT DATA CONTEXT
{data_context_formatted}

---

Structure your analysis using these five sections:

## 1. FRAME THE QUESTION

First, clarify exactly what the user is trying to understand:
- **Core question**: What is the fundamental economic question being asked?
- **Levels vs changes vs direction**: Are they asking about the current level, the rate of change, or where things are heading?
- **Time horizon**: Near-term (next few months), medium-term (1-2 years), or longer-term structural?
- **Implicit assumptions**: What beliefs or concerns might underlie this question?

Be precise. "Is inflation high?" is different from "Is inflation falling?" is different from "Will inflation hit 2%?"

## 2. WHY IS THIS HAPPENING?

Explain the cause-and-effect:
- **Main drivers**: What 2-3 forces are pushing this number up or down?
- **How it works**: Walk through the chain. Example: Fed raises rates -> mortgages get expensive -> people buy fewer homes -> housing prices cool off
- **How long it takes**: These things don't happen overnight.
  - Fed rate changes: 12-18 months to fully hit the economy
  - Government spending: 3-12 months
  - Job market shifts: 6-12 months behind other changes

## 3. WHEN HAVE WE SEEN THIS BEFORE?

Look at history:
- **Similar situations**: When did the economy look like this before? (Give specific years and numbers)
- **What happened then**: How did it turn out?
- **Why today might be different**: What's changed since then?

Don't just look at the most recent example - consider multiple past episodes.

## 4. WHAT'S THE OTHER SIDE?

The data often sends mixed signals:
- **Evidence for**: What supports the main story?
- **Evidence against**: What cuts the other way?
- **Which matters more**: Why should we trust some numbers over others?
- **What we don't know**: What big unknowns could change everything?

If the data is genuinely mixed, say so. Don't pretend to have certainty you don't have.

## 5. WHAT HAPPENS NEXT?

Look ahead:
- **What to watch**: What 2-3 numbers or events will tell us where this is heading?
- **Most likely outcome**: What's probably going to happen?
- **Things could go better if**: What would make the outcome better than expected?
- **Things could go worse if**: What would make it worse?
- **What the Fed is probably thinking**: How are they likely reading this?

Be specific about what would change your view.

---

Remember:
- Be honest about uncertainty - don't pretend to know more than the data shows
- Separate facts from opinions from guesses
- Skip the politics - stick to economics
- If the data is mixed, say so
"""


# =============================================================================
# ANALYSIS TEMPLATES FOR COMMON QUERY TYPES
# =============================================================================

ANALYSIS_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "inflation": {
        "description": "Analysis template for inflation-related questions",
        "key_series": ["CPIAUCSL", "PCEPILFE", "CPILFESL", "T5YIE", "MICH"],
        "frame_guidance": """
Focus on:
- Overall inflation vs "core" (strips out volatile food and gas)
- Goods prices (cars, furniture) vs services (haircuts, rent) - services are stickier
- Rent is 1/3 of the CPI and lags real-world rents by 12+ months
- What do people EXPECT inflation to be? That affects wages and future prices
""",
        "causal_chain_guidance": """
How inflation happens:
- People spend more -> businesses raise prices
- Costs go up (oil, wages) -> businesses pass it on to customers
- If people expect prices to keep rising, they demand higher wages, which... raises prices
- Fed rate hikes take 12-18 months to cool things down
""",
        "historical_context_guidance": """
What's happened before:
- 1970s: Oil shocks + Fed didn't act fast enough = inflation stuck around for a decade
- Early 1980s: Fed raised rates to 20% - crushed inflation but caused a recession
- 2021-2022: Supply chains broke + everyone was spending = worst inflation since the 80s
- 2023-2024: Inflation fell without a recession (so far)
""",
        "forward_look_guidance": """
What to watch:
- Services prices (excluding rent) - this is what the Fed cares about most
- Rent in the CPI - it's falling but slowly (lags actual market rents)
- Wage growth - are workers getting raises that push prices up?
- What's the Fed saying about getting inflation back to 2%?
"""
    },

    "jobs": {
        "description": "Analysis template for employment/labor market questions",
        "key_series": ["PAYEMS", "UNRATE", "JTSJOL", "ICSA", "CES0500000003"],
        "frame_guidance": """
Focus on:
- Jobs ADDED each month vs unemployment RATE - they tell different stories
- Are there lots of job openings? Are enough people looking for work?
- Wages: Are they going up? Faster than inflation?
- Is hiring spread across industries or just a few sectors?
""",
        "causal_chain_guidance": """
How it works:
- Companies post openings -> hire people -> employment goes up
- People quit (good sign - they're confident) or get laid off (bad sign)
- When jobs are plentiful, workers can demand higher pay, which can push up prices
""",
        "historical_context_guidance": """
What's happened before:
- 2019: 3.5% unemployment and wages weren't spiking - more people joined the workforce
- 2020: 22 million jobs lost in 2 months, then the fastest recovery ever
- 2022-2023: Workers had all the power - "Great Resignation"
- Rule of thumb: If unemployment rises 0.5% from its low, a recession usually follows
""",
        "forward_look_guidance": """
What to watch:
- Weekly jobless claims - fastest signal of layoffs
- Job openings per unemployed person - how tight is the job market?
- Are people quitting? (High quits = workers are confident)
- Temp jobs falling often predicts broader weakness
"""
    },

    "recession": {
        "description": "Analysis template for recession risk questions",
        "key_series": ["T10Y2Y", "UNRATE", "SAHMREALTIME", "UMCSENT", "ICSA"],
        "frame_guidance": """
Focus on:
- A recession means the economy shrinks significantly and broadly for several months
- Some indicators warn early (yield curve), others confirm late (unemployment)
- Think in probabilities, not yes/no
- How soon? Next 6 months vs next 1-2 years?
""",
        "causal_chain_guidance": """
How recessions typically happen:
- Long-term rates fall below short-term rates -> banks lend less -> businesses invest less -> layoffs
- A shock hits (oil spike, financial crisis) -> people get scared -> spending drops
- Fed raises rates too much -> crushes demand -> people lose jobs
- Usually: the yield curve inverts 12-18 months BEFORE a recession
""",
        "historical_context_guidance": """
What's happened before:
- 2008-09: Financial crisis - worst since the Great Depression
- 2020: Pandemic - shortest recession ever (2 months)
- 2022-23: Yield curve inverted but no recession (yet)
- False alarms: 1966, 1998 - curve inverted but no recession followed
""",
        "forward_look_guidance": """
What to watch:
- Has unemployment risen 0.5% from its low? That usually means recession
- Are weekly jobless claims spiking?
- Are banks making it harder to get loans?
- Are consumers still spending?
"""
    },

    "fed_policy": {
        "description": "Analysis template for Federal Reserve policy questions",
        "key_series": ["FEDFUNDS", "DGS2", "DGS10", "PCEPILFE", "UNRATE"],
        "frame_guidance": """
Focus on:
- The Fed has two jobs: keep people employed AND keep prices stable
- What data makes the Fed raise or cut rates?
- Where do they think rates are going? Where does Wall Street think?
- How fast will they move? How far?
""",
        "causal_chain_guidance": """
How Fed policy works:
- Fed raises rates -> borrowing gets expensive -> people and businesses spend less
- When the Fed signals future moves, markets adjust before they even act
- Higher rates -> stock/home prices fall -> people feel poorer -> spend less
- Takes 12-18 months for rate changes to fully hit the economy
""",
        "historical_context_guidance": """
What's happened before:
- 2022-23: Fastest rate hikes in 40 years (0% to 5.25%)
- 2019: Fed cut 3 times as "insurance" - no recession needed
- 2013: Fed just MENTIONED slowing bond purchases and markets freaked out
- 1980s: Volcker proved the Fed CAN kill inflation - but it caused a recession
""",
        "forward_look_guidance": """
What to watch:
- Is inflation (core PCE) falling toward 2%?
- Is the job market weakening?
- Do people expect inflation to stay high? (That makes the Fed nervous)
- What's the Fed saying?
"""
    },

    "gdp": {
        "description": "Analysis template for GDP/economic growth questions",
        "key_series": ["GDPC1", "A191RL1Q225SBEA", "A191RO1Q156NBEA", "GDPNOW"],
        "frame_guidance": """
Focus on:
- Year-over-year growth (smoother) vs quarterly growth (timely but jumpy)
- What's driving it? Consumer spending, business investment, government, trade?
- Is this real growth or just inflation making the number look bigger?
- Is the economy running hot (above 2%) or cooling off (below 2%)?
""",
        "causal_chain_guidance": """
What drives GDP:
- Consumer spending is 70% of the economy - when people spend, GDP grows
- Business investment depends on interest rates and confidence
- Government spending can boost or drag on growth
- Trade: Are we exporting more than importing?
""",
        "historical_context_guidance": """
What's happened before:
- Post-2008: Slow recovery, about 2% growth became the new normal
- 2020: Economy shrank 31% in Q2, then bounced 33% in Q3 - wild swings
- 2021-22: Faster-than-normal growth as economy reopened
- Normal: The US economy grows about 2% per year on average
""",
        "forward_look_guidance": """
What to watch:
- Real-time GDP estimates (but they swing around a lot)
- Retail sales - are consumers still spending?
- Factory output - how's the goods economy?
- Jobs report - more jobs = more income = more spending = more growth
"""
    }
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _format_data_context(data_context: Dict[str, Any]) -> str:
    """
    Format data context dictionary into readable string for prompt injection.

    Args:
        data_context: Dictionary of current economic data values

    Returns:
        Formatted string representation of the data
    """
    if not data_context:
        return "No specific data context provided. Use your knowledge of recent economic conditions."

    lines = []
    for key, value in data_context.items():
        # Format the key for readability
        readable_key = key.replace("_", " ").title()

        # Format the value appropriately
        if isinstance(value, float):
            if abs(value) < 10:
                formatted_value = f"{value:.2f}"
            else:
                formatted_value = f"{value:,.1f}"
        elif isinstance(value, dict):
            # Handle nested data (e.g., series with date and value)
            formatted_value = ", ".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, list):
            # Handle list of values (e.g., recent observations)
            formatted_value = ", ".join(str(v) for v in value[:5])
            if len(value) > 5:
                formatted_value += f"... ({len(value)} total)"
        else:
            formatted_value = str(value)

        lines.append(f"- {readable_key}: {formatted_value}")

    return "\n".join(lines)


def _detect_query_type(query: str) -> Optional[str]:
    """
    Detect the type of economic query to select appropriate template.

    Args:
        query: User's economic question

    Returns:
        Query type key (inflation, jobs, recession, fed_policy, gdp) or None
    """
    query_lower = query.lower()

    # Keyword patterns for each query type
    # More specific terms should be listed first for proper matching
    patterns = {
        "inflation": [
            "inflation", "cpi", "pce", "price level", "price index",
            "cost of living", "deflation", "disinflation", "rising prices"
        ],
        "jobs": [
            "job", "employment", "unemployment", "labor", "payroll",
            "hiring", "layoff", "workforce", "wage", "worker"
        ],
        "recession": [
            "recession", "downturn", "contraction", "economic crisis",
            "hard landing", "soft landing", "slowdown"
        ],
        "fed_policy": [
            "fed ", "federal reserve", "interest rate", "rate cut",
            "rate hike", "monetary policy", "fomc", "powell", "tightening",
            "rate decision", "basis points"
        ],
        "gdp": [
            "gdp", "economic growth", "output", "production",
            "economic activity", "expansion", "growing", "growth rate",
            "how fast", "economy grow"
        ]
    }

    # Score each type based on keyword matches
    scores = {}
    for query_type, keywords in patterns.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[query_type] = score

    if not scores:
        return None

    # Return the type with highest score
    return max(scores, key=scores.get)


def _get_template_guidance(query_type: str) -> str:
    """
    Get template-specific guidance for a query type.

    Args:
        query_type: One of the ANALYSIS_TEMPLATES keys

    Returns:
        Formatted guidance string to append to prompt
    """
    if query_type not in ANALYSIS_TEMPLATES:
        return ""

    template = ANALYSIS_TEMPLATES[query_type]

    guidance_parts = [
        f"\n## ANALYSIS GUIDANCE FOR {query_type.upper().replace('_', ' ')} QUESTIONS\n"
    ]

    if "frame_guidance" in template:
        guidance_parts.append(f"### Framing Considerations\n{template['frame_guidance']}")

    if "causal_chain_guidance" in template:
        guidance_parts.append(f"### Causal Chain Notes\n{template['causal_chain_guidance']}")

    if "historical_context_guidance" in template:
        guidance_parts.append(f"### Historical Context Notes\n{template['historical_context_guidance']}")

    if "forward_look_guidance" in template:
        guidance_parts.append(f"### Forward Look Notes\n{template['forward_look_guidance']}")

    return "\n".join(guidance_parts)


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def build_economist_prompt(
    query: str,
    data_context: Dict[str, Any],
    include_template_guidance: bool = True
) -> str:
    """
    Build a structured economist prompt for LLM analysis.

    This function constructs a prompt that guides the LLM to think like a
    credible economist, enforcing a disciplined analytical framework.

    Args:
        query: The user's economic question
        data_context: Dictionary of current economic data values. Can include:
            - Series values: {"cpi_yoy": 2.9, "unemployment": 4.1}
            - Nested data: {"gdp": {"value": 2.8, "date": "2024-Q3"}}
            - Recent observations: {"payrolls": [256000, 180000, 165000]}
        include_template_guidance: Whether to include query-type specific
            guidance from ANALYSIS_TEMPLATES (default: True)

    Returns:
        Complete prompt string ready for LLM input

    Example:
        >>> prompt = build_economist_prompt(
        ...     query="Is inflation coming down?",
        ...     data_context={
        ...         "cpi_yoy": 2.9,
        ...         "core_pce": 2.7,
        ...         "shelter_cpi": 5.2,
        ...         "fed_funds": 5.25
        ...     }
        ... )
        >>> # prompt now contains the full economist analysis template
    """
    # Format the data context
    data_context_formatted = _format_data_context(data_context)

    # Build the base prompt
    prompt = ECONOMIST_PROMPT_TEMPLATE.format(
        query=query,
        data_context_formatted=data_context_formatted
    )

    # Optionally add query-type specific guidance
    if include_template_guidance:
        query_type = _detect_query_type(query)
        if query_type:
            guidance = _get_template_guidance(query_type)
            prompt += guidance

    return prompt


def get_analysis_template(query_type: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the analysis template for a specific query type.

    Args:
        query_type: One of "inflation", "jobs", "recession", "fed_policy", "gdp"

    Returns:
        Template dictionary or None if not found
    """
    return ANALYSIS_TEMPLATES.get(query_type)


def list_template_types() -> list:
    """
    List all available analysis template types.

    Returns:
        List of template type keys
    """
    return list(ANALYSIS_TEMPLATES.keys())


# =============================================================================
# TEST/DEMO
# =============================================================================

if __name__ == "__main__":
    # Test the prompt builder with sample queries

    print("=" * 80)
    print("ECONOMIST PROMPT BUILDER - TEST")
    print("=" * 80)

    # Test 1: Inflation query with data context
    print("\n--- Test 1: Inflation Query ---\n")

    inflation_context = {
        "cpi_yoy": 2.9,
        "core_pce": 2.7,
        "shelter_cpi_yoy": 5.2,
        "fed_funds_rate": 5.25,
        "breakeven_5y": 2.3,
        "recent_cpi_readings": [2.9, 3.0, 3.2, 3.4]
    }

    inflation_prompt = build_economist_prompt(
        query="Is inflation coming down? Will the Fed cut rates soon?",
        data_context=inflation_context
    )

    print(f"Prompt length: {len(inflation_prompt)} characters")
    print("\nFirst 500 characters of prompt:")
    print(inflation_prompt[:500])
    print("...")

    # Test 2: Jobs query
    print("\n--- Test 2: Jobs Query ---\n")

    jobs_context = {
        "unemployment_rate": 4.1,
        "payroll_change": 256000,
        "job_openings": 8.1,  # millions
        "initial_claims": 215000,
        "wage_growth_yoy": 4.2
    }

    jobs_prompt = build_economist_prompt(
        query="How is the job market holding up?",
        data_context=jobs_context
    )

    print(f"Prompt length: {len(jobs_prompt)} characters")
    detected_type = _detect_query_type("How is the job market holding up?")
    print(f"Detected query type: {detected_type}")

    # Test 3: Query type detection
    print("\n--- Test 3: Query Type Detection ---\n")

    test_queries = [
        "Is inflation coming down?",
        "What's happening with the labor market?",
        "Are we heading into a recession?",
        "When will the Fed cut rates?",
        "How fast is the economy growing?",
        "What's the outlook for housing prices?",  # No specific template
    ]

    for q in test_queries:
        query_type = _detect_query_type(q)
        print(f"  '{q}' -> {query_type or 'no specific template'}")

    # Test 4: List templates
    print("\n--- Test 4: Available Templates ---\n")

    for template_type in list_template_types():
        template = get_analysis_template(template_type)
        print(f"  {template_type}:")
        print(f"    Description: {template['description']}")
        print(f"    Key series: {template['key_series']}")

    # Test 5: Empty context
    print("\n--- Test 5: Empty Data Context ---\n")

    empty_prompt = build_economist_prompt(
        query="What's the economic outlook?",
        data_context={}
    )

    print("Empty context message in prompt:")
    print("  'No specific data context provided...' present:",
          "No specific data context provided" in empty_prompt)

    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETED")
    print("=" * 80)
