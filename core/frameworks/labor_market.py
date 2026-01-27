"""
Labor Market Analysis Frameworks

Tools to answer: How strong is the job market? Are we heading for trouble?

What's in here:
1. JOB MARKET BALANCE - Are there more jobs than workers, or vice versa?
   (Economists call this the "Beveridge Curve" but you don't need to remember that)

2. RECESSION EARLY WARNING - Is unemployment rising fast enough to signal a recession?
   (Based on research by economist Claudia Sahm)

3. OVERALL JOB MARKET HEALTH - A combined score: is the job market running hot, cold, or just right?
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import statistics


# =============================================================================
# BEVERIDGE CURVE FRAMEWORK
# =============================================================================

class BeveridgePosition(Enum):
    """Classification of labor market tightness based on Beveridge curve position."""
    VERY_TIGHT = "very_tight"      # High vacancies, low unemployment
    TIGHT = "tight"                 # Above-trend vacancies relative to unemployment
    BALANCED = "balanced"           # Near historical norm
    SLACK = "slack"                 # Below-trend vacancies relative to unemployment
    VERY_SLACK = "very_slack"       # Low vacancies, high unemployment


# Required FRED series for Beveridge Curve analysis
BEVERIDGE_CURVE_SERIES = [
    "JTSJOL",   # Job Openings: Total Nonfarm (thousands)
    "UNRATE",   # Unemployment Rate (percent)
]

# Thresholds for Beveridge curve interpretation
# Based on historical ranges (2001-2024)
BEVERIDGE_THRESHOLDS = {
    "vacancy_rate_high": 7.0,       # Job openings as % of labor force
    "vacancy_rate_low": 3.0,
    "unemployment_low": 4.0,        # Percent
    "unemployment_high": 6.0,
    "matching_efficiency_shift": 0.5,  # Standard deviations from trend
}


def calculate_beveridge_curve(data: Dict) -> Dict:
    """
    Calculate Beveridge curve position and matching efficiency.

    The Beveridge curve describes the inverse relationship between job vacancies
    and unemployment. A tight labor market shows high vacancies with low
    unemployment (upper-left), while a slack market shows the opposite (lower-right).

    Outward shifts in the curve (same unemployment but higher vacancies) indicate
    reduced matching efficiency - workers and jobs are having trouble connecting.
    This can signal structural changes like skills mismatches or geographic
    immobility.

    Args:
        data: Dictionary containing:
            - 'JTSJOL': Job openings level (thousands) or list of recent values
            - 'UNRATE': Unemployment rate (percent) or list of recent values
            - 'labor_force': Labor force level (thousands), optional
            - 'historical_vacancy_rates': List of historical vacancy rates, optional
            - 'historical_unemployment': List of historical unemployment rates, optional

    Returns:
        Dictionary with:
            - vacancy_rate: Current job openings as % of labor force
            - unemployment_rate: Current unemployment rate
            - position: BeveridgePosition enum value
            - vacancies_per_unemployed: Ratio of openings to unemployed persons
            - matching_efficiency_deviation: How far from historical trend
            - curve_shift_detected: Boolean if significant outward shift
    """
    # Extract current values (handle both single values and lists)
    jtsjol = data.get("JTSJOL")
    unrate = data.get("UNRATE")

    if isinstance(jtsjol, list):
        jtsjol = jtsjol[-1] if jtsjol else None
    if isinstance(unrate, list):
        unrate = unrate[-1] if unrate else None

    if jtsjol is None or unrate is None:
        return {"error": "Missing required data: JTSJOL and UNRATE"}

    # Calculate vacancy rate (job openings as % of labor force)
    # Default labor force ~165 million if not provided
    labor_force = data.get("labor_force", 165000)
    vacancy_rate = (jtsjol / labor_force) * 100

    # Calculate vacancies per unemployed person
    unemployed_level = data.get("UNEMPLOY")
    if unemployed_level is None:
        # Estimate from unemployment rate and labor force
        unemployed_level = (unrate / 100) * labor_force
    vacancies_per_unemployed = jtsjol / unemployed_level if unemployed_level > 0 else 0

    # Determine Beveridge curve position
    position = _classify_beveridge_position(vacancy_rate, unrate)

    # Calculate matching efficiency deviation
    # Compare current vacancy rate to what historical trend would predict
    historical_vr = data.get("historical_vacancy_rates", [])
    historical_ur = data.get("historical_unemployment", [])

    matching_efficiency_deviation = 0.0
    curve_shift_detected = False

    if len(historical_vr) >= 12 and len(historical_ur) >= 12:
        # Simple regression-based approach: predict vacancy rate from unemployment
        # and compare to actual
        predicted_vr = _predict_vacancy_rate_from_history(
            unrate, historical_ur, historical_vr
        )
        if predicted_vr is not None:
            deviation = vacancy_rate - predicted_vr
            std_dev = statistics.stdev(historical_vr) if len(historical_vr) > 1 else 1.0
            matching_efficiency_deviation = deviation / std_dev if std_dev > 0 else 0
            curve_shift_detected = abs(matching_efficiency_deviation) > BEVERIDGE_THRESHOLDS["matching_efficiency_shift"]

    return {
        "vacancy_rate": round(vacancy_rate, 2),
        "unemployment_rate": round(unrate, 2),
        "position": position,
        "vacancies_per_unemployed": round(vacancies_per_unemployed, 2),
        "matching_efficiency_deviation": round(matching_efficiency_deviation, 2),
        "curve_shift_detected": curve_shift_detected,
    }


def _classify_beveridge_position(vacancy_rate: float, unemployment_rate: float) -> BeveridgePosition:
    """Classify position on the Beveridge curve based on vacancy and unemployment rates."""
    vr_high = BEVERIDGE_THRESHOLDS["vacancy_rate_high"]
    vr_low = BEVERIDGE_THRESHOLDS["vacancy_rate_low"]
    ur_high = BEVERIDGE_THRESHOLDS["unemployment_high"]
    ur_low = BEVERIDGE_THRESHOLDS["unemployment_low"]

    if vacancy_rate >= vr_high and unemployment_rate <= ur_low:
        return BeveridgePosition.VERY_TIGHT
    elif vacancy_rate >= vr_low and unemployment_rate <= ur_high:
        if vacancy_rate > (vr_high + vr_low) / 2 or unemployment_rate < (ur_high + ur_low) / 2:
            return BeveridgePosition.TIGHT
        return BeveridgePosition.BALANCED
    elif vacancy_rate <= vr_low and unemployment_rate >= ur_high:
        return BeveridgePosition.VERY_SLACK
    elif vacancy_rate < (vr_high + vr_low) / 2 and unemployment_rate > (ur_high + ur_low) / 2:
        return BeveridgePosition.SLACK
    else:
        return BeveridgePosition.BALANCED


def _predict_vacancy_rate_from_history(
    current_ur: float,
    historical_ur: List[float],
    historical_vr: List[float]
) -> Optional[float]:
    """Simple linear prediction of vacancy rate from unemployment rate using historical data."""
    n = len(historical_ur)
    if n < 2 or len(historical_vr) < 2:
        return None

    # Use min of both lists
    n = min(n, len(historical_vr))
    ur = historical_ur[:n]
    vr = historical_vr[:n]

    # Simple linear regression
    ur_mean = statistics.mean(ur)
    vr_mean = statistics.mean(vr)

    numerator = sum((ur[i] - ur_mean) * (vr[i] - vr_mean) for i in range(n))
    denominator = sum((ur[i] - ur_mean) ** 2 for i in range(n))

    if denominator == 0:
        return vr_mean

    slope = numerator / denominator
    intercept = vr_mean - slope * ur_mean

    return slope * current_ur + intercept


def interpret_beveridge_curve(result: Dict) -> str:
    """
    Explain job market balance in plain English - like a smart friend would.

    Args:
        result: Output from calculate_beveridge_curve()

    Returns:
        Human-readable interpretation that anyone can understand.
    """
    if "error" in result:
        return f"Can't analyze job market balance: {result['error']}"

    position = result["position"]
    vr = result["vacancy_rate"]
    ur = result["unemployment_rate"]
    vpu = result["vacancies_per_unemployed"]
    shift = result["curve_shift_detected"]

    # Position interpretation - written like you're explaining to a friend
    position_text = {
        BeveridgePosition.VERY_TIGHT: (
            f"Workers have the upper hand right now. There are {vpu} job openings "
            f"for every unemployed person - companies are fighting over workers. "
            f"Unemployment is just {ur}%, and employers are desperate to hire. "
            f"If you're job hunting, this is a great time to negotiate."
        ),
        BeveridgePosition.TIGHT: (
            f"The job market favors workers. With {vpu} openings per unemployed person "
            f"and unemployment at {ur}%, finding work is easier than usual. "
            f"Employers may have trouble filling positions quickly."
        ),
        BeveridgePosition.BALANCED: (
            f"The job market is in a healthy balance. There are about {vpu} job openings "
            f"per unemployed person, and the {ur}% unemployment rate is close to normal. "
            f"Neither workers nor employers have a big advantage."
        ),
        BeveridgePosition.SLACK: (
            f"Job seekers face a tougher market. With only {vpu} openings per unemployed "
            f"person and unemployment at {ur}%, competition for jobs is real. "
            f"It may take longer to find the right opportunity."
        ),
        BeveridgePosition.VERY_SLACK: (
            f"The job market is rough for workers. Only {vpu} openings exist per "
            f"unemployed person, and unemployment sits at {ur}%. Companies have the "
            f"leverage, and job searches will likely take longer."
        ),
    }

    interpretation = position_text.get(position, "Unable to assess job market balance.")

    # Add matching efficiency commentary - but explain what it actually means
    if shift:
        deviation = result["matching_efficiency_deviation"]
        if deviation > 0:
            interpretation += (
                "\n\nSomething unusual: Companies are struggling to fill jobs even "
                "more than the unemployment rate would suggest. This could mean "
                "workers don't have the skills employers need, jobs are in the wrong "
                "places, or people are rethinking what kind of work they want. "
                "The job market isn't connecting workers to jobs as smoothly as it used to."
            )
        else:
            interpretation += (
                "\n\nGood news: Workers and jobs are finding each other more efficiently "
                "than usual. The job matching process seems to be working well."
            )

    return interpretation


# =============================================================================
# SAHM RULE FRAMEWORK
# =============================================================================

# Required FRED series for Sahm Rule
SAHM_RULE_SERIES = [
    "UNRATE",   # Unemployment Rate (percent)
]

# Sahm Rule threshold
SAHM_THRESHOLD = 0.50  # 0.5 percentage point rise triggers recession signal


def calculate_sahm_rule(data: Dict) -> Dict:
    """
    Calculate the Sahm Rule recession indicator.

    The Sahm Rule identifies the start of a recession when the 3-month moving
    average of the national unemployment rate rises by 0.50 percentage points
    or more relative to its low during the previous 12 months.

    This indicator was developed by economist Claudia Sahm and has accurately
    identified every U.S. recession since 1970 in real-time. It triggers near
    the start of recessions, making it valuable for timely policy response.

    Economic logic: When unemployment begins rising meaningfully from its
    recent low, it typically signals the start of a self-reinforcing downturn
    where job losses lead to reduced spending, causing further job losses.

    Args:
        data: Dictionary containing:
            - 'UNRATE': List of at least 15 monthly unemployment rates
                       (most recent last), or single current value with
                       'unrate_3mo_avg' and 'unrate_12mo_low' provided

    Returns:
        Dictionary with:
            - current_3mo_avg: 3-month average unemployment rate
            - twelve_month_low: Lowest 3-month avg in prior 12 months
            - sahm_value: Current Sahm indicator value
            - threshold: Trigger threshold (0.50)
            - triggered: Boolean if recession signal is on
            - distance_to_trigger: How far from triggering (negative = already triggered)
            - risk_level: 'low', 'elevated', 'high', or 'triggered'
    """
    unrate_data = data.get("UNRATE")

    # Handle pre-calculated values
    if isinstance(unrate_data, (int, float)):
        current_3mo_avg = data.get("unrate_3mo_avg", unrate_data)
        twelve_month_low = data.get("unrate_12mo_low")
        if twelve_month_low is None:
            return {"error": "Need either 15 months of UNRATE data or unrate_12mo_low"}
    elif isinstance(unrate_data, list):
        if len(unrate_data) < 15:
            return {"error": f"Need at least 15 months of unemployment data, got {len(unrate_data)}"}

        # Calculate 3-month averages
        three_month_avgs = []
        for i in range(len(unrate_data) - 2):
            avg = statistics.mean(unrate_data[i:i+3])
            three_month_avgs.append(avg)

        current_3mo_avg = three_month_avgs[-1]
        # Look at 12 months of 3-month averages before the current one
        prior_12_month_avgs = three_month_avgs[-13:-1] if len(three_month_avgs) >= 13 else three_month_avgs[:-1]
        twelve_month_low = min(prior_12_month_avgs) if prior_12_month_avgs else current_3mo_avg
    else:
        return {"error": "UNRATE must be a number or list of monthly values"}

    # Calculate Sahm indicator
    sahm_value = current_3mo_avg - twelve_month_low
    triggered = sahm_value >= SAHM_THRESHOLD
    distance_to_trigger = SAHM_THRESHOLD - sahm_value

    # Classify risk level
    if triggered:
        risk_level = "triggered"
    elif sahm_value >= 0.3:
        risk_level = "high"
    elif sahm_value >= 0.2:
        risk_level = "elevated"
    else:
        risk_level = "low"

    return {
        "current_3mo_avg": round(current_3mo_avg, 2),
        "twelve_month_low": round(twelve_month_low, 2),
        "sahm_value": round(sahm_value, 2),
        "threshold": SAHM_THRESHOLD,
        "triggered": triggered,
        "distance_to_trigger": round(distance_to_trigger, 2),
        "risk_level": risk_level,
    }


def interpret_sahm_rule(result: Dict) -> str:
    """
    Explain recession early warning in plain English.

    The core idea: When unemployment starts rising quickly from its recent low,
    bad things tend to follow. This has correctly flagged every US recession since 1970.

    Args:
        result: Output from calculate_sahm_rule()

    Returns:
        Human-readable explanation anyone can understand.
    """
    if "error" in result:
        return f"Can't check recession early warning: {result['error']}"

    sahm = result["sahm_value"]
    threshold = result["threshold"]
    current_avg = result["current_3mo_avg"]
    low = result["twelve_month_low"]
    distance = result["distance_to_trigger"]
    triggered = result["triggered"]
    risk = result["risk_level"]

    if triggered:
        interpretation = (
            f"RECESSION WARNING TRIGGERED. Unemployment is rising fast enough to signal "
            f"a recession may be starting. Here's what happened: unemployment climbed from "
            f"a low of {low}% to {current_avg}% - a {sahm:.2f} percentage point jump. "
            f"That crosses the {threshold} point threshold that has preceded every US recession "
            f"since 1970. This doesn't guarantee a recession, but historically, when unemployment "
            f"rises this fast, the economy is usually already in trouble."
        )
    elif risk == "high":
        interpretation = (
            f"Getting close to recession warning territory. Unemployment has risen from "
            f"{low}% to {current_avg}% - we're now just {distance:.2f} points away from the "
            f"threshold that has historically signaled recessions. Not there yet, but the "
            f"trend is concerning. Worth watching closely over the next few months."
        )
    elif risk == "elevated":
        interpretation = (
            f"Unemployment is creeping up, but not fast enough to trigger recession alarms. "
            f"It's risen from {low}% to {current_avg}% - still {distance:.2f} points below "
            f"the danger zone. Think of it as a yellow light: pay attention, but don't panic."
        )
    else:
        interpretation = (
            f"No recession warning here. Unemployment at {current_avg}% is barely changed from "
            f"its recent low of {low}%. We're {distance:.2f} points away from the level that "
            f"would signal trouble. The job market looks stable."
        )

    return interpretation


# =============================================================================
# LABOR MARKET HEAT FRAMEWORK
# =============================================================================

# Required FRED series for Labor Market Heat
LABOR_MARKET_HEAT_SERIES = [
    "JTSQUR",      # Quits Rate: Total Nonfarm (percent)
    "JTSJOL",      # Job Openings: Total Nonfarm (thousands)
    "UNEMPLOY",    # Unemployment Level (thousands)
    "LNS12300060", # Employment-Population Ratio - 25-54 Yrs (percent)
]

# Historical benchmarks for heat indicators (approximate 2015-2019 averages as "normal")
HEAT_BENCHMARKS = {
    "quits_rate_hot": 2.4,        # Above this = very confident workers
    "quits_rate_normal": 2.2,     # Pre-pandemic average
    "quits_rate_cold": 1.8,       # Below this = workers scared to leave

    "openings_per_unemployed_hot": 1.2,    # Above this = very tight
    "openings_per_unemployed_normal": 0.8, # Balanced
    "openings_per_unemployed_cold": 0.5,   # Below this = slack

    "prime_epop_hot": 80.5,       # Near historical highs
    "prime_epop_normal": 79.0,    # 2019 level
    "prime_epop_cold": 76.0,      # Significant slack

    "wage_productivity_gap_hot": 1.0,    # Wages outpacing productivity
    "wage_productivity_gap_cold": -1.0,  # Wages lagging badly
}


def calculate_labor_market_heat(data: Dict) -> Dict:
    """
    Calculate a composite measure of labor market tightness.

    This framework combines multiple indicators to assess overall labor market
    conditions, as no single metric tells the full story:

    1. Quits Rate: When workers voluntarily leave jobs at high rates, it signals
       confidence in finding new/better positions. Low quits suggest fear.

    2. Job Openings per Unemployed: A direct measure of labor market tightness.
       Values above 1.0 mean more open jobs than job seekers.

    3. Prime-Age Employment-Population Ratio (25-54): Measures labor market
       utilization without demographic distortions from aging population or
       changing school enrollment.

    4. Wage Growth vs Productivity: When wage growth exceeds productivity gains,
       it suggests excess labor demand (and potential inflation pressure).

    Args:
        data: Dictionary containing:
            - 'JTSQUR': Quits rate (percent)
            - 'JTSJOL': Job openings (thousands)
            - 'UNEMPLOY': Unemployment level (thousands)
            - 'LNS12300060': Prime-age employment-population ratio (percent)
            - 'wage_growth': Optional - year-over-year wage growth (percent)
            - 'productivity_growth': Optional - productivity growth (percent)

    Returns:
        Dictionary with component scores, composite heat index, and classification.
    """
    # Extract values
    quits_rate = data.get("JTSQUR")
    job_openings = data.get("JTSJOL")
    unemployed = data.get("UNEMPLOY")
    prime_epop = data.get("LNS12300060")
    wage_growth = data.get("wage_growth")
    productivity_growth = data.get("productivity_growth")

    # Handle list inputs (take most recent)
    if isinstance(quits_rate, list):
        quits_rate = quits_rate[-1] if quits_rate else None
    if isinstance(job_openings, list):
        job_openings = job_openings[-1] if job_openings else None
    if isinstance(unemployed, list):
        unemployed = unemployed[-1] if unemployed else None
    if isinstance(prime_epop, list):
        prime_epop = prime_epop[-1] if prime_epop else None

    result = {
        "components": {},
        "component_scores": {},
        "missing_components": [],
    }

    # Score each component on a -2 to +2 scale
    # Negative = cold/slack, Positive = hot/tight
    scores = []

    # 1. Quits Rate
    if quits_rate is not None:
        result["components"]["quits_rate"] = round(quits_rate, 2)
        quits_score = _score_indicator(
            quits_rate,
            cold=HEAT_BENCHMARKS["quits_rate_cold"],
            normal=HEAT_BENCHMARKS["quits_rate_normal"],
            hot=HEAT_BENCHMARKS["quits_rate_hot"]
        )
        result["component_scores"]["quits_rate"] = round(quits_score, 2)
        scores.append(quits_score)
    else:
        result["missing_components"].append("JTSQUR")

    # 2. Job Openings per Unemployed
    if job_openings is not None and unemployed is not None and unemployed > 0:
        openings_per_unemployed = job_openings / unemployed
        result["components"]["openings_per_unemployed"] = round(openings_per_unemployed, 2)
        opu_score = _score_indicator(
            openings_per_unemployed,
            cold=HEAT_BENCHMARKS["openings_per_unemployed_cold"],
            normal=HEAT_BENCHMARKS["openings_per_unemployed_normal"],
            hot=HEAT_BENCHMARKS["openings_per_unemployed_hot"]
        )
        result["component_scores"]["openings_per_unemployed"] = round(opu_score, 2)
        scores.append(opu_score)
    else:
        if job_openings is None:
            result["missing_components"].append("JTSJOL")
        if unemployed is None:
            result["missing_components"].append("UNEMPLOY")

    # 3. Prime-Age EPOP
    if prime_epop is not None:
        result["components"]["prime_epop"] = round(prime_epop, 2)
        epop_score = _score_indicator(
            prime_epop,
            cold=HEAT_BENCHMARKS["prime_epop_cold"],
            normal=HEAT_BENCHMARKS["prime_epop_normal"],
            hot=HEAT_BENCHMARKS["prime_epop_hot"]
        )
        result["component_scores"]["prime_epop"] = round(epop_score, 2)
        scores.append(epop_score)
    else:
        result["missing_components"].append("LNS12300060")

    # 4. Wage-Productivity Gap (optional but informative)
    if wage_growth is not None and productivity_growth is not None:
        wage_prod_gap = wage_growth - productivity_growth
        result["components"]["wage_productivity_gap"] = round(wage_prod_gap, 2)
        wpg_score = _score_indicator(
            wage_prod_gap,
            cold=HEAT_BENCHMARKS["wage_productivity_gap_cold"],
            normal=0.0,
            hot=HEAT_BENCHMARKS["wage_productivity_gap_hot"]
        )
        result["component_scores"]["wage_productivity_gap"] = round(wpg_score, 2)
        scores.append(wpg_score)

    # Calculate composite heat index
    if scores:
        heat_index = statistics.mean(scores)
        result["heat_index"] = round(heat_index, 2)
        result["classification"] = _classify_heat(heat_index)
    else:
        result["heat_index"] = None
        result["classification"] = "insufficient_data"

    return result


def _score_indicator(value: float, cold: float, normal: float, hot: float) -> float:
    """
    Score an indicator on a -2 to +2 scale.

    -2 = very cold (well below normal)
    -1 = cold (below normal)
     0 = normal
    +1 = hot (above normal)
    +2 = very hot (well above normal)
    """
    if value >= hot:
        # How far above hot threshold
        excess = value - hot
        range_size = hot - normal
        additional = min(excess / range_size, 1.0) if range_size > 0 else 0
        return 1.0 + additional
    elif value >= normal:
        # Between normal and hot
        return (value - normal) / (hot - normal) if hot != normal else 0
    elif value >= cold:
        # Between cold and normal
        return -((normal - value) / (normal - cold)) if normal != cold else 0
    else:
        # Below cold
        deficit = cold - value
        range_size = normal - cold
        additional = min(deficit / range_size, 1.0) if range_size > 0 else 0
        return -1.0 - additional


def _classify_heat(heat_index: float) -> str:
    """Classify overall labor market heat based on composite index."""
    if heat_index >= 1.5:
        return "overheating"
    elif heat_index >= 0.5:
        return "hot"
    elif heat_index >= -0.5:
        return "balanced"
    elif heat_index >= -1.5:
        return "cooling"
    else:
        return "cold"


def interpret_labor_market_heat(result: Dict) -> str:
    """
    Explain overall job market health in plain English.

    Think of it like a thermostat: Is the job market running hot (great for workers,
    but might cause inflation)? Cold (tough for job seekers)? Or just right?

    Args:
        result: Output from calculate_labor_market_heat()

    Returns:
        Human-readable explanation anyone can understand.
    """
    if result.get("classification") == "insufficient_data":
        missing = result.get("missing_components", [])
        return f"Not enough data to assess job market health. Missing: {', '.join(missing)}"

    heat_index = result["heat_index"]
    classification = result["classification"]
    components = result["components"]
    scores = result["component_scores"]

    # Overall assessment - conversational, not academic
    heat_descriptions = {
        "overheating": (
            f"The job market is running too hot. Workers have enormous leverage right now - "
            f"companies are desperate to hire and wages are surging. Great if you're looking "
            f"for a raise, but this kind of heat often leads to inflation problems. "
            f"The Fed is probably watching this closely."
        ),
        "hot": (
            f"It's a workers' market. Companies are hiring aggressively, and people who want "
            f"jobs can generally find them. If you're employed, you have real bargaining power "
            f"for raises or better conditions. Wages are likely rising faster than usual."
        ),
        "balanced": (
            f"The job market is in a healthy sweet spot. There's enough demand for workers "
            f"to keep unemployment low, but not so much that wages spiral out of control. "
            f"This is roughly what economists consider 'full employment.'"
        ),
        "cooling": (
            f"The job market is cooling off. Hiring has slowed, and workers don't have quite "
            f"as much leverage as before. Job searches might take a bit longer. This could be "
            f"fine (a soft landing) or the early stages of something worse - worth monitoring."
        ),
        "cold": (
            f"The job market is weak. Finding work is harder, and employers have the upper hand "
            f"in negotiations. People are less likely to quit for new opportunities. "
            f"Wage growth is probably sluggish, and job security feels shakier."
        ),
    }

    interpretation = heat_descriptions.get(classification, "Can't assess overall job market health.")

    # Add component details - explain what each signal means
    details = []

    if "quits_rate" in components:
        qr = components["quits_rate"]
        qs = scores["quits_rate"]
        if qs > 0.5:
            details.append(
                f"People are quitting jobs at a {qr}% rate - they're confident they can "
                f"find something better. That's a sign of a strong market."
            )
        elif qs < -0.5:
            details.append(
                f"Few people are quitting (just {qr}%) - workers are playing it safe, "
                f"which suggests they're worried about finding new jobs."
            )

    if "openings_per_unemployed" in components:
        opu = components["openings_per_unemployed"]
        if opu > 1.0:
            details.append(
                f"There are {opu} open jobs for every unemployed person. "
                f"More jobs than job seekers = workers have options."
            )
        else:
            details.append(
                f"Only {opu} open jobs per unemployed person. "
                f"More people looking than jobs available = tougher competition."
            )

    if "prime_epop" in components:
        epop = components["prime_epop"]
        es = scores["prime_epop"]
        if es > 0.5:
            details.append(
                f"{epop}% of prime working-age adults (25-54) have jobs - "
                f"that's historically high, meaning the economy is pulling people into work."
            )
        elif es < -0.5:
            details.append(
                f"Only {epop}% of prime working-age adults have jobs - "
                f"there's room to bring more people into the workforce."
            )

    if "wage_productivity_gap" in components:
        gap = components["wage_productivity_gap"]
        if gap > 0.5:
            details.append(
                f"Wages are rising {gap:.1f} points faster than productivity. "
                f"Great for workers, but it adds fuel to inflation."
            )
        elif gap < -0.5:
            details.append(
                f"Wages are trailing productivity by {abs(gap):.1f} points. "
                f"Less inflation pressure, but workers aren't sharing in productivity gains."
            )

    if details:
        interpretation += "\n\nWhat the signals tell us:\n- " + "\n- ".join(details)

    if result["missing_components"]:
        interpretation += f"\n\n(Some data unavailable: {', '.join(result['missing_components'])})"

    return interpretation


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_all_required_series() -> List[str]:
    """Return deduplicated list of all FRED series required for labor market analysis."""
    all_series = set()
    all_series.update(BEVERIDGE_CURVE_SERIES)
    all_series.update(SAHM_RULE_SERIES)
    all_series.update(LABOR_MARKET_HEAT_SERIES)
    return sorted(list(all_series))


def analyze_labor_market(data: Dict) -> Dict:
    """
    Run all labor market frameworks and return consolidated results.

    Args:
        data: Dictionary containing all required FRED series data

    Returns:
        Dictionary with results from all frameworks
    """
    return {
        "beveridge_curve": {
            "result": calculate_beveridge_curve(data),
            "interpretation": interpret_beveridge_curve(calculate_beveridge_curve(data)),
        },
        "sahm_rule": {
            "result": calculate_sahm_rule(data),
            "interpretation": interpret_sahm_rule(calculate_sahm_rule(data)),
        },
        "labor_market_heat": {
            "result": calculate_labor_market_heat(data),
            "interpretation": interpret_labor_market_heat(calculate_labor_market_heat(data)),
        },
        "required_series": get_all_required_series(),
    }


# =============================================================================
# TESTS WITH SAMPLE DATA
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("LABOR MARKET ANALYSIS FRAMEWORKS - TEST SUITE")
    print("=" * 70)

    # Sample data representing a tight labor market (similar to 2022-2023)
    tight_market_data = {
        "JTSJOL": 10500,  # 10.5 million job openings
        "UNRATE": [3.4, 3.5, 3.4, 3.6, 3.7, 3.6, 3.5, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0, 4.1],
        "UNEMPLOY": 6500,  # 6.5 million unemployed
        "labor_force": 165000,  # 165 million
        "JTSQUR": 2.6,  # High quits rate
        "LNS12300060": 80.8,  # Strong prime-age employment
        "wage_growth": 5.0,
        "productivity_growth": 1.5,
        "historical_vacancy_rates": [4.5, 4.8, 5.0, 5.2, 5.5, 5.8, 6.0, 6.2, 6.5, 6.8, 7.0, 6.8],
        "historical_unemployment": [6.0, 5.5, 5.2, 4.8, 4.5, 4.2, 4.0, 3.8, 3.6, 3.5, 3.4, 3.5],
    }

    print("\n" + "-" * 70)
    print("TEST 1: BEVERIDGE CURVE - Tight Labor Market")
    print("-" * 70)
    bev_result = calculate_beveridge_curve(tight_market_data)
    print(f"Result: {bev_result}")
    print(f"\nInterpretation:\n{interpret_beveridge_curve(bev_result)}")

    print("\n" + "-" * 70)
    print("TEST 2: SAHM RULE - No Recession Signal")
    print("-" * 70)
    sahm_result = calculate_sahm_rule(tight_market_data)
    print(f"Result: {sahm_result}")
    print(f"\nInterpretation:\n{interpret_sahm_rule(sahm_result)}")

    print("\n" + "-" * 70)
    print("TEST 3: LABOR MARKET HEAT - Hot Market")
    print("-" * 70)
    heat_result = calculate_labor_market_heat(tight_market_data)
    print(f"Result: {heat_result}")
    print(f"\nInterpretation:\n{interpret_labor_market_heat(heat_result)}")

    # Sample data representing recession conditions
    recession_data = {
        "JTSJOL": 4000,  # Low job openings
        "UNRATE": [3.5, 3.6, 3.8, 4.0, 4.3, 4.6, 5.0, 5.4, 5.8, 6.2, 6.5, 6.8, 7.0, 7.2, 7.5],
        "UNEMPLOY": 12000,  # 12 million unemployed
        "labor_force": 160000,
        "JTSQUR": 1.6,  # Low quits
        "LNS12300060": 75.0,  # Weak prime-age employment
        "wage_growth": 2.0,
        "productivity_growth": 1.0,
    }

    print("\n" + "-" * 70)
    print("TEST 4: BEVERIDGE CURVE - Slack Market")
    print("-" * 70)
    bev_result2 = calculate_beveridge_curve(recession_data)
    print(f"Result: {bev_result2}")
    print(f"\nInterpretation:\n{interpret_beveridge_curve(bev_result2)}")

    print("\n" + "-" * 70)
    print("TEST 5: SAHM RULE - Recession Triggered")
    print("-" * 70)
    sahm_result2 = calculate_sahm_rule(recession_data)
    print(f"Result: {sahm_result2}")
    print(f"\nInterpretation:\n{interpret_sahm_rule(sahm_result2)}")

    print("\n" + "-" * 70)
    print("TEST 6: LABOR MARKET HEAT - Cold Market")
    print("-" * 70)
    heat_result2 = calculate_labor_market_heat(recession_data)
    print(f"Result: {heat_result2}")
    print(f"\nInterpretation:\n{interpret_labor_market_heat(heat_result2)}")

    print("\n" + "-" * 70)
    print("TEST 7: ALL REQUIRED FRED SERIES")
    print("-" * 70)
    print(f"Required series: {get_all_required_series()}")

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)
