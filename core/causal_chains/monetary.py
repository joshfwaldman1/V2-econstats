"""
Monetary Policy Transmission Chains.

Structured representations of how Federal Reserve policy affects the economy
through various transmission mechanisms. Each chain models the sequence of
effects with typical lag times and relevant FRED series.

Chains:
1. RATE_TO_HOUSING - Fed policy → housing market → shelter inflation
2. RATE_TO_CONSUMPTION - Fed policy → credit conditions → consumer spending
3. RATE_TO_LABOR - Fed policy → business conditions → labor market

Usage:
    from core.causal_chains.monetary import (
        RATE_TO_HOUSING,
        RATE_TO_CONSUMPTION,
        RATE_TO_LABOR,
        detect_chain_position,
        explain_chain_position
    )

    position = detect_chain_position(RATE_TO_HOUSING, data)
    explanation = explain_chain_position('RATE_TO_HOUSING', position)
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta


# =============================================================================
# CHAIN DEFINITIONS
# Each stage has:
#   - stage: Human-readable description
#   - lag: Expected time range from Fed action to this stage responding
#   - series: Primary FRED series to monitor this stage
#   - direction: Expected direction of change when Fed HIKES (+ = increase, - = decrease)
#   - threshold: Minimum % change to consider "activated" (for rates/indices)
# =============================================================================

RATE_TO_HOUSING = [
    {
        'stage': 'Fed raises rates',
        'lag': 'immediate',
        'lag_months': (0, 0),
        'series': 'FEDFUNDS',
        'direction': '+',
        'threshold': 0.25,
        'description': 'The Fed raises its benchmark interest rate. This is the starting gun for everything else.'
    },
    {
        'stage': 'Mortgage rates jump',
        'lag': 'within weeks',
        'lag_months': (0, 1),
        'series': 'DGS10',
        'direction': '+',
        'threshold': 0.10,
        'description': 'Mortgage rates are tied to Treasury yields, which respond almost immediately to Fed moves.'
    },
    {
        'stage': 'Buying a home gets expensive',
        'lag': '1-2 months',
        'lag_months': (0, 2),
        'series': 'MORTGAGE30US',
        'direction': '+',
        'threshold': 0.25,
        'description': 'Higher mortgage rates mean higher monthly payments. A jump from 3% to 7% can add $1,000+/month to a typical mortgage.'
    },
    {
        'stage': 'Fewer people buy homes',
        'lag': '2-6 months',
        'lag_months': (2, 6),
        'series': 'EXHOSLUSM495S',  # Existing home sales
        'direction': '-',
        'threshold': -5.0,
        'description': 'When monthly payments double, many buyers drop out. Existing home sales fall as people wait for better rates.'
    },
    {
        'stage': 'Home prices start cooling',
        'lag': '6-12 months',
        'lag_months': (6, 12),
        'series': 'CSUSHPINSA',  # Case-Shiller
        'direction': '-',
        'threshold': -2.0,
        'description': 'With fewer buyers competing, sellers lose pricing power. Price growth slows or turns negative in hot markets.'
    },
    {
        'stage': 'Rent inflation finally slows',
        'lag': '1-2 years',
        'lag_months': (12, 24),
        'series': 'CUSR0000SAH1',  # Shelter CPI
        'direction': '-',
        'threshold': -1.0,
        'description': 'This takes forever because the government measures what people are actually paying, not new lease prices. Most renters are locked into year-long leases at old prices, so it takes 1-2 years for lower market rents to show up in the official numbers.'
    },
    {
        'stage': 'Overall inflation comes down',
        'lag': '1.5-2.5 years',
        'lag_months': (18, 30),
        'series': 'CPILFESL',  # Core CPI
        'direction': '-',
        'threshold': -0.5,
        'description': 'Housing costs are about 40% of core inflation. Once rent inflation cools, it pulls down the whole inflation number. This is why rate hikes take so long to work.'
    }
]


RATE_TO_CONSUMPTION = [
    {
        'stage': 'Fed raises rates',
        'lag': 'immediate',
        'lag_months': (0, 0),
        'series': 'FEDFUNDS',
        'direction': '+',
        'threshold': 0.25,
        'description': 'The Fed raises its benchmark rate. Credit card companies and lenders respond almost instantly.'
    },
    {
        'stage': 'Credit cards get more expensive',
        'lag': 'immediate',
        'lag_months': (0, 0),
        'series': 'TERMCBCCALLNS',  # Credit card interest rate
        'direction': '+',
        'threshold': 0.25,
        'description': 'Credit card rates are variable and move with the Fed. If you carry a balance, you feel this right away.'
    },
    {
        'stage': 'Car loans cost more',
        'lag': 'within weeks',
        'lag_months': (0, 1),
        'series': 'TERMCBPER24NS',  # 24-month auto loan rate
        'direction': '+',
        'threshold': 0.25,
        'description': 'Auto loan rates rise, adding hundreds of dollars per year to car payments. This makes people think twice about buying new cars.'
    },
    {
        'stage': 'Big purchases slow down',
        'lag': '3-6 months',
        'lag_months': (3, 6),
        'series': 'DGORDER',  # Durable goods orders
        'direction': '-',
        'threshold': -3.0,
        'description': 'Cars, appliances, furniture - anything you might finance. When borrowing costs more, people delay these purchases or buy cheaper options.'
    },
    {
        'stage': 'Overall spending cools',
        'lag': '6-12 months',
        'lag_months': (6, 12),
        'series': 'PCE',  # Personal consumption expenditures
        'direction': '-',
        'threshold': -1.0,
        'description': 'Eventually, higher rates slow down spending across the board. This is how the Fed cools inflation - by making people spend less.'
    }
]


RATE_TO_LABOR = [
    {
        'stage': 'Fed raises rates',
        'lag': 'immediate',
        'lag_months': (0, 0),
        'series': 'FEDFUNDS',
        'direction': '+',
        'threshold': 0.25,
        'description': 'The Fed raises rates. Businesses start thinking about what higher borrowing costs mean for their plans.'
    },
    {
        'stage': 'Borrowing gets harder',
        'lag': '1-3 months',
        'lag_months': (0, 3),
        'series': 'NFCI',  # Chicago Fed Financial Conditions Index
        'direction': '+',
        'threshold': 0.1,
        'description': 'Banks tighten lending standards. Loans cost more and are harder to get. Companies that relied on cheap money start feeling the squeeze.'
    },
    {
        'stage': 'Companies cut back on expansion',
        'lag': '6-12 months',
        'lag_months': (6, 12),
        'series': 'PNFI',  # Private nonresidential fixed investment
        'direction': '-',
        'threshold': -2.0,
        'description': 'That new factory? The office expansion? Companies put projects on hold when borrowing is expensive. Why invest now if financing costs eat into returns?'
    },
    {
        'stage': 'Hiring slows down',
        'lag': '9-15 months',
        'lag_months': (9, 15),
        'series': 'PAYEMS',  # Nonfarm payrolls (look at MoM change)
        'direction': '-',
        'threshold': -50,  # Thousands
        'description': 'Companies get cautious. They still add jobs, but fewer than before. Monthly job gains shrink from 300K to 150K, then lower.'
    },
    {
        'stage': 'Companies stop posting jobs',
        'lag': '9-15 months',
        'lag_months': (9, 15),
        'series': 'JTSJOL',  # JOLTS job openings (leading indicator)
        'direction': '-',
        'threshold': -500,  # Thousands
        'description': 'Job openings drop before layoffs start. Companies pull back on hiring plans first - it is easier than firing people. This is an early warning sign.'
    },
    {
        'stage': 'Unemployment rises',
        'lag': '1-2 years',
        'lag_months': (12, 24),
        'series': 'UNRATE',  # Unemployment rate (lagging indicator)
        'direction': '+',
        'threshold': 0.3,
        'description': 'The last domino. Unemployment only rises after everything else has slowed. By the time you see it in headlines, the economy has been cooling for a year.'
    }
]


# Chain lookup for convenience
CHAINS = {
    'RATE_TO_HOUSING': RATE_TO_HOUSING,
    'RATE_TO_CONSUMPTION': RATE_TO_CONSUMPTION,
    'RATE_TO_LABOR': RATE_TO_LABOR
}


# =============================================================================
# CHAIN POSITION DETECTION
# =============================================================================

def detect_chain_position(chain: list, data: dict,
                          rate_hike_date: Optional[str] = None) -> dict:
    """
    Detect where we are in a monetary policy transmission chain.

    Args:
        chain: One of the chain definitions (e.g., RATE_TO_HOUSING)
        data: Dictionary of series data, keyed by series ID.
              Each value should have 'values' (list of floats) and
              'dates' (list of date strings) keys.
        rate_hike_date: Optional start date of rate hiking cycle (YYYY-MM-DD).
                        If not provided, attempts to detect from FEDFUNDS data.

    Returns:
        dict with:
            - 'current_stage': Index of current stage (0-based)
            - 'stage_name': Name of current stage
            - 'months_since_hike': Estimated months since hiking began
            - 'stages_activated': List of stages that show expected response
            - 'stages_pending': List of stages not yet responding
            - 'next_stage': Expected next stage
            - 'next_stage_timing': When to expect next stage
            - 'stage_details': Per-stage analysis
    """
    result = {
        'current_stage': 0,
        'stage_name': chain[0]['stage'],
        'months_since_hike': 0,
        'stages_activated': [],
        'stages_pending': [],
        'next_stage': None,
        'next_stage_timing': None,
        'stage_details': []
    }

    # Try to detect hiking start from FEDFUNDS data if not provided
    if rate_hike_date is None:
        rate_hike_date = _detect_hike_start(data.get('FEDFUNDS', {}))

    # Calculate months since hike
    if rate_hike_date:
        try:
            hike_dt = datetime.strptime(rate_hike_date, '%Y-%m-%d')
            months_since = (datetime.now() - hike_dt).days / 30.44
            result['months_since_hike'] = int(months_since)
        except (ValueError, TypeError):
            pass

    # Analyze each stage
    for i, stage in enumerate(chain):
        series_id = stage['series']
        series_data = data.get(series_id, {})

        stage_analysis = {
            'stage': stage['stage'],
            'series': series_id,
            'lag_range': stage['lag'],
            'expected_direction': stage['direction'],
            'status': 'unknown',
            'recent_change': None,
            'activated': False
        }

        # Check if we have data for this series
        if series_data and 'values' in series_data:
            change = _calculate_recent_change(series_data, stage)
            stage_analysis['recent_change'] = change

            # Check if the change matches expected direction and exceeds threshold
            if change is not None:
                threshold = stage['threshold']
                if stage['direction'] == '+':
                    activated = change >= threshold
                else:  # direction == '-'
                    activated = change <= threshold

                stage_analysis['activated'] = activated
                if activated:
                    stage_analysis['status'] = 'responding'
                    result['stages_activated'].append(stage['stage'])
                else:
                    stage_analysis['status'] = 'not yet'
                    result['stages_pending'].append(stage['stage'])
        else:
            stage_analysis['status'] = 'no data'
            result['stages_pending'].append(stage['stage'])

        result['stage_details'].append(stage_analysis)

    # Determine current stage (last activated stage)
    for i, detail in enumerate(result['stage_details']):
        if detail['activated']:
            result['current_stage'] = i
            result['stage_name'] = chain[i]['stage']

    # Determine next expected stage
    if result['current_stage'] < len(chain) - 1:
        next_idx = result['current_stage'] + 1
        result['next_stage'] = chain[next_idx]['stage']

        # Calculate when to expect it
        lag_low, lag_high = chain[next_idx]['lag_months']
        months_since = result['months_since_hike']

        if months_since < lag_low:
            result['next_stage_timing'] = f"in {lag_low - months_since} to {lag_high - months_since} months"
        elif months_since <= lag_high:
            result['next_stage_timing'] = "expected now through " + f"{lag_high - months_since} more months"
        else:
            result['next_stage_timing'] = "overdue (expected by now)"

    return result


def _detect_hike_start(fedfunds_data: dict) -> Optional[str]:
    """
    Detect the start of a rate hiking cycle from FEDFUNDS data.

    Looks for the first significant rate increase after a period of stability.
    Returns the date of that increase.
    """
    if not fedfunds_data or 'values' not in fedfunds_data or 'dates' not in fedfunds_data:
        return None

    values = fedfunds_data['values']
    dates = fedfunds_data['dates']

    if len(values) < 3:
        return None

    # Look for rate increases of at least 0.25% from a low base
    for i in range(1, len(values)):
        if values[i] - values[i-1] >= 0.20:  # At least ~25bp increase
            # Check if previous rate was near zero (or low)
            if values[i-1] < 1.0:
                return dates[i]

    # Fallback: find the minimum rate and return the date of first increase after
    min_rate = min(values)
    min_idx = values.index(min_rate)

    for i in range(min_idx + 1, len(values)):
        if values[i] > min_rate + 0.20:
            return dates[i]

    return None


def _calculate_recent_change(series_data: dict, stage: dict) -> Optional[float]:
    """
    Calculate the recent change in a series to assess if it's responding.

    For rates (FEDFUNDS, mortgage, etc.): absolute change in level
    For indices (CPI, home prices): YoY % change in the rate of change
    For levels (job openings, payrolls): absolute change
    """
    values = series_data.get('values', [])

    if len(values) < 2:
        return None

    series_id = stage['series']

    # For rates - look at level change over past 12 months
    if series_id in ('FEDFUNDS', 'DGS10', 'MORTGAGE30US', 'TERMCBCCALLNS',
                     'TERMCBPER24NS', 'UNRATE', 'NFCI'):
        # Compare current to 12 months ago (or as far back as we have)
        lookback = min(12, len(values) - 1)
        current = values[-1]
        past = values[-(lookback + 1)]
        return current - past

    # For indices - calculate YoY change
    if series_id in ('CPILFESL', 'CUSR0000SAH1', 'CSUSHPINSA'):
        if len(values) >= 13:
            current = values[-1]
            year_ago = values[-13]
            if year_ago > 0:
                return ((current - year_ago) / year_ago) * 100
        return None

    # For levels (activity data) - YoY change
    if series_id in ('EXHOSLUSM495S', 'DGORDER', 'PCE', 'PNFI', 'JTSJOL'):
        if len(values) >= 13:
            current = values[-1]
            year_ago = values[-13]
            if year_ago > 0:
                return ((current - year_ago) / year_ago) * 100
        elif len(values) >= 2:
            # Short data - use available change
            return ((values[-1] - values[0]) / values[0]) * 100 if values[0] > 0 else None
        return None

    # For payrolls - MoM change (in thousands)
    if series_id == 'PAYEMS':
        if len(values) >= 2:
            return values[-1] - values[-2]
        return None

    # Default: simple difference
    return values[-1] - values[0] if len(values) >= 2 else None


# =============================================================================
# CHAIN POSITION EXPLANATION
# =============================================================================

def explain_chain_position(chain_name: str, position: dict) -> str:
    """
    Generate a plain English explanation of the current position in a chain.

    Args:
        chain_name: One of 'RATE_TO_HOUSING', 'RATE_TO_CONSUMPTION', 'RATE_TO_LABOR'
        position: Result from detect_chain_position()

    Returns:
        Human-readable explanation suitable for a briefing.
    """
    chain = CHAINS.get(chain_name)
    if not chain:
        return f"Unknown chain: {chain_name}"

    months = position.get('months_since_hike', 0)
    current_stage = position.get('current_stage', 0)
    stage_name = position.get('stage_name', 'Unknown')
    activated = position.get('stages_activated', [])
    pending = position.get('stages_pending', [])
    next_stage = position.get('next_stage')
    next_timing = position.get('next_stage_timing')

    # Build the explanation based on chain type
    if chain_name == 'RATE_TO_HOUSING':
        return _explain_housing_chain(months, current_stage, stage_name,
                                       activated, pending, next_stage, next_timing,
                                       position.get('stage_details', []))

    elif chain_name == 'RATE_TO_CONSUMPTION':
        return _explain_consumption_chain(months, current_stage, stage_name,
                                           activated, pending, next_stage, next_timing,
                                           position.get('stage_details', []))

    elif chain_name == 'RATE_TO_LABOR':
        return _explain_labor_chain(months, current_stage, stage_name,
                                     activated, pending, next_stage, next_timing,
                                     position.get('stage_details', []))

    return f"Chain analysis not available for {chain_name}"


def _explain_housing_chain(months: int, current_stage: int, stage_name: str,
                           activated: list, pending: list, next_stage: str,
                           next_timing: str, details: list) -> str:
    """Generate explanation for the housing transmission chain."""

    parts = []

    # Opening context - conversational
    if months > 0:
        if months < 6:
            parts.append(f"It's been about {months} months since the Fed started raising rates.")
        elif months < 12:
            parts.append(f"We're about {months} months in - still early in the process.")
        elif months < 24:
            parts.append(f"It's been {months} months. We're in the middle of the cycle, where the real effects start showing up.")
        else:
            parts.append(f"It's been {months} months - we should be seeing the full effects by now.")

    # Current status based on stage - tell a story
    if current_stage == 0:
        parts.append("The Fed raised rates, but the housing market hasn't felt it yet. Give it a few months.")

    elif current_stage <= 2:
        parts.append("Mortgage rates have jumped, and buying a home just got a lot more expensive.")
        parts.append("A rate increase from 3% to 7% can add over $1,000 to a monthly payment on a typical home.")
        if 'Fewer people buy homes' in pending:
            parts.append("Home sales haven't dropped yet, but they will - buyers are doing the math.")

    elif current_stage == 3:
        parts.append("Home sales have dropped. Fewer buyers can qualify for mortgages at these rates, and many are waiting for prices to fall.")
        if 'Home prices start cooling' in pending:
            parts.append("Prices are still high, but with fewer buyers competing, they should start cooling soon.")

    elif current_stage == 4:
        parts.append("Home prices are finally starting to cool. With fewer buyers bidding, sellers are losing their pricing power.")
        if 'Rent inflation finally slows' in pending:
            parts.append("Here's the frustrating part: rent inflation in the official numbers won't drop for another 6-12 months.")
            parts.append("Why? The government measures what renters are actually paying, and most are locked into leases signed when rents were higher.")

    elif current_stage == 5:
        parts.append("Rent inflation is finally starting to cool in the official numbers.")
        parts.append("This is a big deal - housing costs are about 40% of core inflation. As they come down, overall inflation follows.")
        if 'Overall inflation comes down' in pending:
            parts.append("We should see this pull down core inflation over the next 6-12 months.")

    elif current_stage == 6:
        parts.append("The full cycle is complete. Lower housing costs are now pulling down overall inflation.")
        parts.append("This is what the Fed was waiting for - the slow, grinding path from rate hikes to lower inflation.")

    # Forward look - make it useful
    if next_stage and next_timing and 'overdue' not in next_timing:
        parts.append(f"What's next: {next_stage.lower()} should happen {next_timing}.")
    elif next_stage and 'overdue' in str(next_timing):
        parts.append(f"Heads up: We'd normally expect to see {next_stage.lower()} by now. Something unusual might be going on.")

    return " ".join(parts)


def _explain_consumption_chain(months: int, current_stage: int, stage_name: str,
                                activated: list, pending: list, next_stage: str,
                                next_timing: str, details: list) -> str:
    """Generate explanation for the consumption transmission chain."""

    parts = []

    if months > 0:
        parts.append(f"It's been {months} months since rates started rising.")

    if current_stage <= 2:
        parts.append("If you carry a credit card balance or need a car loan, you're already feeling this.")
        parts.append("Credit card rates jumped right away - they're tied to the Fed's rate.")
        parts.append("Auto loans cost a lot more too, which adds up over a 5-year loan.")
        if 'Big purchases slow down' in pending:
            parts.append("People haven't stopped buying cars and appliances yet, but give it a few months.")

    elif current_stage == 3:
        parts.append("People are pulling back on big purchases. Car sales are down, and appliance orders are slowing.")
        parts.append("Makes sense - when financing costs more, that new car or kitchen renovation can wait.")
        if 'Overall spending cools' in pending:
            parts.append("Once big-ticket spending slows, overall consumer spending usually follows in 3-6 months.")

    elif current_stage == 4:
        parts.append("Consumer spending has slowed across the board.")
        parts.append("This is actually what the Fed wants - when people spend less, businesses can't raise prices as easily, and inflation comes down.")
        parts.append("The tricky part is slowing things down just enough without causing a recession.")

    if next_stage and next_timing and 'overdue' not in next_timing:
        parts.append(f"What's next: {next_stage.lower()} should happen {next_timing}.")

    return " ".join(parts)


def _explain_labor_chain(months: int, current_stage: int, stage_name: str,
                         activated: list, pending: list, next_stage: str,
                         next_timing: str, details: list) -> str:
    """Generate explanation for the labor market transmission chain."""

    parts = []

    if months > 0:
        parts.append(f"It's been {months} months since rates started rising.")

    if current_stage <= 1:
        parts.append("Banks are getting pickier about who they lend to, and loans cost more.")
        parts.append("Companies that were counting on cheap money to fund growth are rethinking their plans.")
        if 'Companies cut back on expansion' in pending:
            parts.append("Watch for business investment to slow over the next 3-9 months - that new factory or office expansion might get postponed.")

    elif current_stage == 2:
        parts.append("Companies are putting expansion plans on hold. Why borrow at 8% to build something that might return 10%? The math doesn't work anymore.")
        if 'Hiring slows down' in pending:
            parts.append("Hiring usually slows next. Companies get cautious before they stop adding jobs.")

    elif current_stage <= 4:
        if 'Hiring slows down' in activated or 'Companies stop posting jobs' in activated:
            parts.append("The job market is cooling. Fewer job postings, slower hiring.")
            parts.append("Here's the thing: job openings drop before layoffs start. Companies pull back on new hires first - it's easier than letting people go.")
        if 'Unemployment rises' in pending:
            parts.append("Unemployment hasn't spiked yet. That's usually the last domino to fall.")

    elif current_stage == 5:
        parts.append("Unemployment is rising now. The job market has clearly softened.")
        parts.append("This is usually when the Fed starts thinking about cutting rates. Their job is done - maybe too well if unemployment rises too fast.")

    if next_stage and next_timing:
        if 'overdue' not in next_timing:
            parts.append(f"What's next: {next_stage.lower()} should happen {next_timing}.")
        else:
            parts.append(f"Interesting: We'd normally expect {next_stage.lower()} by now. The job market has been surprisingly resilient.")

    return " ".join(parts)


def _list_to_prose(items: list) -> str:
    """Convert a list to prose (e.g., ['a', 'b', 'c'] -> 'a, b, and c')."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0].lower()
    if len(items) == 2:
        return f"{items[0].lower()} and {items[1].lower()}"
    return ", ".join(item.lower() for item in items[:-1]) + f", and {items[-1].lower()}"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_chain_series(chain_name: str) -> list:
    """Get all FRED series IDs needed to analyze a chain."""
    chain = CHAINS.get(chain_name)
    if not chain:
        return []
    return [stage['series'] for stage in chain]


def get_all_chain_series() -> list:
    """Get all unique FRED series IDs across all chains."""
    all_series = set()
    for chain in CHAINS.values():
        for stage in chain:
            all_series.add(stage['series'])
    return list(all_series)


def summarize_all_chains(data: dict, rate_hike_date: Optional[str] = None) -> dict:
    """
    Analyze all chains and return a summary.

    Args:
        data: Dictionary of series data, keyed by series ID
        rate_hike_date: Optional start of hiking cycle

    Returns:
        Dictionary with summary for each chain
    """
    summary = {}
    for chain_name, chain in CHAINS.items():
        position = detect_chain_position(chain, data, rate_hike_date)
        explanation = explain_chain_position(chain_name, position)
        summary[chain_name] = {
            'position': position,
            'explanation': explanation
        }
    return summary


# =============================================================================
# TESTS
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MONETARY POLICY TRANSMISSION CHAINS - TEST")
    print("=" * 70)

    # Test 1: Chain definitions
    print("\n1. CHAIN DEFINITIONS")
    print("-" * 40)

    for chain_name, chain in CHAINS.items():
        print(f"\n{chain_name}:")
        for i, stage in enumerate(chain):
            print(f"  {i+1}. {stage['stage']} ({stage['lag']}) - {stage['series']}")

    # Test 2: Get all series needed
    print("\n\n2. SERIES REQUIRED FOR ALL CHAINS")
    print("-" * 40)
    all_series = get_all_chain_series()
    print(f"Total unique series: {len(all_series)}")
    print(f"Series: {sorted(all_series)}")

    # Test 3: Simulate chain detection with mock data
    print("\n\n3. CHAIN POSITION DETECTION (SIMULATED DATA)")
    print("-" * 40)

    # Mock data simulating ~12 months after hike start (March 2022 cycle)
    mock_data = {
        'FEDFUNDS': {
            'values': [0.08, 0.08, 0.33, 0.77, 1.21, 1.68, 2.33, 3.08, 3.83, 4.33, 4.57, 4.83, 5.08, 5.33],
            'dates': ['2022-01-01', '2022-02-01', '2022-03-01', '2022-04-01', '2022-05-01',
                      '2022-06-01', '2022-07-01', '2022-08-01', '2022-09-01', '2022-10-01',
                      '2022-11-01', '2022-12-01', '2023-01-01', '2023-02-01']
        },
        'DGS10': {
            'values': [1.78, 1.93, 2.14, 2.78, 2.84, 2.98, 2.90, 2.90, 3.52, 4.07, 3.87, 3.62, 3.52, 3.92],
            'dates': ['2022-01-01', '2022-02-01', '2022-03-01', '2022-04-01', '2022-05-01',
                      '2022-06-01', '2022-07-01', '2022-08-01', '2022-09-01', '2022-10-01',
                      '2022-11-01', '2022-12-01', '2023-01-01', '2023-02-01']
        },
        'MORTGAGE30US': {
            'values': [3.45, 3.76, 4.16, 5.10, 5.30, 5.52, 5.54, 5.66, 6.11, 7.08, 6.95, 6.42, 6.27, 6.50],
            'dates': ['2022-01-01', '2022-02-01', '2022-03-01', '2022-04-01', '2022-05-01',
                      '2022-06-01', '2022-07-01', '2022-08-01', '2022-09-01', '2022-10-01',
                      '2022-11-01', '2022-12-01', '2023-01-01', '2023-02-01']
        },
        'EXHOSLUSM495S': {
            'values': [6.49, 6.02, 5.77, 5.61, 5.41, 5.12, 4.81, 4.71, 4.43, 4.43, 4.09, 4.02, 4.0, 4.08],
            'dates': ['2022-01-01', '2022-02-01', '2022-03-01', '2022-04-01', '2022-05-01',
                      '2022-06-01', '2022-07-01', '2022-08-01', '2022-09-01', '2022-10-01',
                      '2022-11-01', '2022-12-01', '2023-01-01', '2023-02-01']
        },
        'CSUSHPINSA': {
            'values': [280, 285, 290, 295, 300, 305, 305, 303, 300, 298, 297, 296, 295, 294],
            'dates': ['2022-01-01', '2022-02-01', '2022-03-01', '2022-04-01', '2022-05-01',
                      '2022-06-01', '2022-07-01', '2022-08-01', '2022-09-01', '2022-10-01',
                      '2022-11-01', '2022-12-01', '2023-01-01', '2023-02-01']
        },
        # Shelter CPI - still rising in this simulation (lagged response)
        'CUSR0000SAH1': {
            'values': [100, 100.5, 101.0, 101.6, 102.2, 102.9, 103.6, 104.3, 105.0, 105.8, 106.5, 107.2, 107.9, 108.5],
            'dates': ['2022-01-01', '2022-02-01', '2022-03-01', '2022-04-01', '2022-05-01',
                      '2022-06-01', '2022-07-01', '2022-08-01', '2022-09-01', '2022-10-01',
                      '2022-11-01', '2022-12-01', '2023-01-01', '2023-02-01']
        }
    }

    # Detect position in housing chain
    print("\nRATE_TO_HOUSING Chain:")
    position = detect_chain_position(RATE_TO_HOUSING, mock_data, rate_hike_date='2022-03-01')

    print(f"  Months since hike: {position['months_since_hike']}")
    print(f"  Current stage: {position['current_stage']} - {position['stage_name']}")
    print(f"  Stages activated: {position['stages_activated']}")
    print(f"  Stages pending: {position['stages_pending']}")
    print(f"  Next stage: {position['next_stage']}")
    print(f"  Next timing: {position['next_stage_timing']}")

    # Test 4: Plain English explanation
    print("\n\n4. PLAIN ENGLISH EXPLANATION")
    print("-" * 40)

    explanation = explain_chain_position('RATE_TO_HOUSING', position)
    print(f"\n{explanation}")

    # Test 5: Test other chains with minimal data
    print("\n\n5. OTHER CHAIN EXPLANATIONS (MINIMAL DATA)")
    print("-" * 40)

    for chain_name in ['RATE_TO_CONSUMPTION', 'RATE_TO_LABOR']:
        position = detect_chain_position(CHAINS[chain_name], mock_data, rate_hike_date='2022-03-01')
        explanation = explain_chain_position(chain_name, position)
        print(f"\n{chain_name}:")
        print(f"  {explanation}")

    # Test 6: Hike detection
    print("\n\n6. RATE HIKE DETECTION")
    print("-" * 40)
    detected_hike = _detect_hike_start(mock_data['FEDFUNDS'])
    print(f"Detected hike start: {detected_hike}")

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)
