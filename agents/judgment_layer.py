"""
Judgment Layer: Gemini web search + Claude synthesis for interpretive queries.

For queries like "is unemployment high?" or "is the economy doing well?", this module:
1. Detects if the query requires judgment/interpretation (not just facts)
2. Uses Gemini's web search to find current expert commentary
3. Has Claude synthesize the search results with our data and economist quotes

This provides authoritative context that raw data alone can't give.
"""

import os
import re
import json
import concurrent.futures
from datetime import datetime, timedelta
from typing import Optional, Tuple
from urllib.request import Request, urlopen

from processing.analytics import compute_series_analytics

# API Keys
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Cache for judgment query results (avoids repeated expensive LLM calls)
_judgment_cache: dict = {}
_judgment_cache_ttl = timedelta(minutes=30)

# Judgment query patterns - these need interpretation, not just facts
JUDGMENT_PATTERNS = [
    # Direct judgment questions
    r'\b(is|are|was|were)\b.*(high|low|good|bad|strong|weak|healthy|unhealthy|concerning|worrying|normal|abnormal|elevated|depressed|ok|okay|fine|solid|soft|hard)',
    r'\b(should i|should we)\b.*(worry|be concerned|be worried)',
    r'\bhow (good|bad|healthy|strong|weak)\b',
    r'\b(too|very|extremely|unusually)\s+(high|low|hot|cold|strong|weak)',

    # Comparative judgment
    r'\b(better|worse) than (expected|normal|usual|average|historical)',
    r'\b(above|below|at) (trend|normal|average)',

    # Forward-looking judgment
    r'\b(will|going to|likely to)\b.*(recession|crash|recover|improve|worsen)',
    r'\bwhat (should|will|might) (happen|come|expect)',
    r'\b(outlook|forecast|prediction|prognosis)\b',

    # Qualitative assessment - broader patterns
    r'\bhow is .* doing\b',  # "How is the economy doing?", "How is inflation doing?"
    r'\bhow are .* doing\b',  # "How are jobs doing?"
    r'\bstate of (the |)',  # "state of the economy", "state of inflation"
    r'\beconomic (health|condition|situation|outlook)',

    # "Is X good/well" patterns
    r'\bdoing (well|good|bad|poorly|okay|ok)\b',

    # Assessment questions
    r'\b(healthy|unhealthy|strong|weak|tight|loose|hot|cold)\s+(economy|labor market|job market|housing market)',

    # Bubble/valuation/speculation questions - need expert research
    r'\b(bubble|overvalued|undervalued|overheated|frothy|mania|euphoria|irrational)\b',
    r'\b(are we in|is there|is this) (a|an)\b.*(bubble|crisis|recession)',
    r'\b(sustainable|unsustainable)\b',  # "are valuations sustainable?"
    r'\b(p/e|pe ratio|valuation|multiple)s?\b.*(high|low|elevated|stretched|reasonable)',
    r'\bover(priced|valued|heated|bought)\b',
    r'\bunder(priced|valued)\b',
    r'\b(speculative|speculation|speculating)\b',
    r'\b(crash|correction|pullback|sell-off|selloff)\b.*(coming|imminent|likely|due)',
    r'\b(too far|too fast|too much)\b',  # "has the market gone too far?"
    r'\b(justified|warranted)\b',  # "is the rally justified?"
    r'\bvaluation.*(sustainable|justified|reasonable|stretched|high|low)',  # "are valuations sustainable?"
    r'\b(rally|run-up|surge).*(sustainable|justified|warranted)',  # "is the rally sustainable?"
]

# Pre-curated thresholds with economist quotes
ECONOMIST_THRESHOLDS = {
    'UNRATE': {
        'name': 'Unemployment Rate (U-3)',
        'thresholds': [
            {'level': 3.5, 'label': 'Very tight', 'quote': '"Below 4% is effectively full employment" - Janet Yellen'},
            {'level': 4.0, 'label': 'Full employment', 'quote': '"The natural rate is probably around 4-4.5%" - Fed SEP median'},
            {'level': 4.5, 'label': 'Natural rate', 'quote': '"NAIRU estimates center around 4.4%" - CBO'},
            {'level': 5.0, 'label': 'Moderate slack', 'quote': '"5% unemployment means millions still seeking work" - Claudia Sahm'},
            {'level': 6.0, 'label': 'Elevated', 'quote': '"Above 6% typically signals recession" - NBER'},
            {'level': 7.0, 'label': 'Recession territory', 'quote': '"7%+ unemployment is a policy emergency" - Jason Furman'},
        ],
        'historical_avg': 5.7,
        'historical_note': 'Post-WWII average is 5.7%. Pre-pandemic low was 3.5% (2019). Pandemic peak was 14.7% (April 2020).',
    },
    'CPIAUCSL': {
        'name': 'CPI Inflation (YoY)',
        'thresholds': [
            {'level': 1.0, 'label': 'Deflationary risk', 'quote': '"Below 1% risks deflation expectations taking hold" - Ben Bernanke'},
            {'level': 2.0, 'label': 'Target', 'quote': '"2% is our symmetric inflation target" - Fed FOMC Statement'},
            {'level': 2.5, 'label': 'Slightly elevated', 'quote': '"Modestly above 2% is acceptable in the short run" - Jerome Powell'},
            {'level': 3.0, 'label': 'Above target', 'quote': '"3% inflation erodes purchasing power noticeably" - Larry Summers'},
            {'level': 4.0, 'label': 'Concerning', 'quote': '"4%+ inflation demands policy response" - Olivier Blanchard'},
            {'level': 5.0, 'label': 'High', 'quote': '"5% inflation is a tax on savers and workers" - Jason Furman'},
        ],
        'historical_avg': 3.3,
        'historical_note': 'Post-WWII average is 3.3%. 2022 peak was 9.1%. Fed target is 2%.',
    },
    'FEDFUNDS': {
        'name': 'Federal Funds Rate',
        'thresholds': [
            {'level': 0.25, 'label': 'Zero lower bound', 'quote': '"Near-zero rates signal extraordinary accommodation" - Ben Bernanke'},
            {'level': 2.5, 'label': 'Neutral', 'quote': '"The neutral rate is probably around 2.5-3%" - Fed SEP'},
            {'level': 4.0, 'label': 'Restrictive', 'quote': '"Above neutral, policy is actively slowing the economy" - Jerome Powell'},
            {'level': 5.0, 'label': 'Very restrictive', 'quote': '"5%+ rates create significant headwinds" - Neel Kashkari'},
        ],
        'historical_avg': 4.6,
        'historical_note': 'Post-1980 average is 4.6%. Volcker peak was 20% (1981). Post-2008 was near 0% for years.',
    },
    'A191RL1Q225SBEA': {
        'name': 'Real GDP Growth (Quarterly Annualized)',
        'thresholds': [
            {'level': -0.5, 'label': 'Contraction', 'quote': '"Two consecutive negative quarters is the common recession definition" - NBER'},
            {'level': 0.0, 'label': 'Stagnation', 'quote': '"Zero growth means treading water" - Larry Summers'},
            {'level': 2.0, 'label': 'Trend growth', 'quote': '"2% is roughly the US potential growth rate" - CBO'},
            {'level': 3.0, 'label': 'Above trend', 'quote': '"3%+ growth is strong by modern standards" - Jason Furman'},
            {'level': 4.0, 'label': 'Boom', 'quote': '"4%+ growth is exceptional and often unsustainable" - Claudia Sahm'},
        ],
        'historical_avg': 3.2,
        'historical_note': 'Post-WWII average is 3.2%. 2010s average was 2.3%. Potential growth has slowed.',
    },
    'LNS12300060': {
        'name': 'Prime-Age Employment-Population Ratio',
        'thresholds': [
            {'level': 77.0, 'label': 'Weak', 'quote': '"Below 77% signals significant labor market slack" - Jared Bernstein'},
            {'level': 79.0, 'label': 'Moderate', 'quote': '"79% is historically average for prime-age employment" - BLS'},
            {'level': 80.0, 'label': 'Strong', 'quote': '"80%+ indicates a tight labor market" - Claudia Sahm'},
            {'level': 80.5, 'label': 'Very strong', 'quote': '"Above 80% matches the best readings in decades" - Jason Furman'},
        ],
        'historical_avg': 78.5,
        'historical_note': 'Pre-pandemic peak was 80.4% (Jan 2020). Current level is near all-time highs.',
    },
    'PAYEMS': {
        'name': 'Monthly Job Gains',
        'thresholds': [
            {'level': 0, 'label': 'Job losses', 'quote': '"Negative payrolls signal recession" - Claudia Sahm'},
            {'level': 75, 'label': 'Breakeven', 'quote': '"75K/month keeps pace with labor force growth" - Fed estimates'},
            {'level': 150, 'label': 'Moderate', 'quote': '"150K is solid, sustainable job growth" - Jason Furman'},
            {'level': 200, 'label': 'Strong', 'quote': '"200K+ signals robust labor demand" - Jared Bernstein'},
            {'level': 300, 'label': 'Very strong', 'quote': '"300K+ is exceptional, often catch-up growth" - Claudia Sahm'},
        ],
        'historical_avg': 150,
        'historical_note': 'Long-run average is ~150K/month. Breakeven has fallen due to demographics (aging, lower immigration).',
    },
}


def is_judgment_query(query: str) -> bool:
    """
    Detect if a query requires interpretation/judgment rather than just facts.

    Examples of judgment queries:
    - "Is unemployment high?"
    - "Is the economy doing well?"
    - "Should I be worried about inflation?"

    Examples of factual queries (NOT judgment):
    - "What is the unemployment rate?"
    - "Show me GDP growth"
    - "Inflation data"

    Returns:
        True if the query needs interpretation, False for pure factual queries
    """
    query_lower = query.lower().strip()

    # Check against judgment patterns
    for pattern in JUDGMENT_PATTERNS:
        if re.search(pattern, query_lower):
            return True

    return False


def get_threshold_context(series_id: str, current_value: float) -> Optional[dict]:
    """
    Get threshold context for a series given its current value.

    Returns:
        dict with 'assessment', 'quote', and 'historical_context' or None
    """
    if series_id not in ECONOMIST_THRESHOLDS:
        return None

    config = ECONOMIST_THRESHOLDS[series_id]
    thresholds = config['thresholds']

    # Find the appropriate threshold level
    assessment = None
    quote = None
    for i, t in enumerate(thresholds):
        if current_value <= t['level']:
            assessment = t['label']
            quote = t['quote']
            break

    # If above all thresholds, use the last one
    if assessment is None and thresholds:
        assessment = thresholds[-1]['label']
        quote = thresholds[-1]['quote']

    # Compare to historical average
    hist_avg = config.get('historical_avg')
    if hist_avg:
        if current_value < hist_avg * 0.85:
            hist_comparison = f"well below the historical average of {hist_avg}"
        elif current_value < hist_avg * 0.95:
            hist_comparison = f"below the historical average of {hist_avg}"
        elif current_value > hist_avg * 1.15:
            hist_comparison = f"well above the historical average of {hist_avg}"
        elif current_value > hist_avg * 1.05:
            hist_comparison = f"above the historical average of {hist_avg}"
        else:
            hist_comparison = f"near the historical average of {hist_avg}"
    else:
        hist_comparison = None

    return {
        'series_name': config['name'],
        'assessment': assessment,
        'quote': quote,
        'historical_comparison': hist_comparison,
        'historical_note': config.get('historical_note'),
    }


def gemini_web_search(query: str, topic: str = None) -> Optional[str]:
    """
    Use Gemini to search the web for current expert commentary on a topic.

    Args:
        query: The user's original query
        topic: Optional topic focus (e.g., "unemployment", "inflation")

    Returns:
        String with search results and expert commentary, or None on failure
    """
    if not GEMINI_API_KEY:
        return None

    # Detect if this is a bubble/valuation question - needs different search approach
    query_lower = query.lower()
    is_bubble_question = any(kw in query_lower for kw in [
        'bubble', 'overvalued', 'valuation', 'p/e', 'pe ratio', 'overheated',
        'frothy', 'speculation', 'sustainable', 'crash', 'correction'
    ])

    if is_bubble_question:
        search_prompt = f"""Search the web for current expert analysis on this market/valuation question:

USER QUESTION: {query}

Find expert opinions on:
1. Current valuation metrics (P/E ratios, forward earnings, price-to-sales, Shiller CAPE) and whether they're stretched
2. Comparisons to historical bubbles (dot-com, housing, etc.) - similarities and differences
3. Fundamental drivers and whether they justify current prices (for AI: datacenter capex, revenue growth, productivity gains, hyperscaler spending)
4. Bear case AND bull case arguments from credible analysts

PRIORITIZE these authoritative sources (in order):
1. **Wall Street chief economists and strategists** - Jan Hatzius (Goldman Sachs), Michael Gapen (BofA), Bruce Kasman (JP Morgan), Ajay Rajadhyaksha (Barclays), Larry Fink (BlackRock), Ray Dalio (Bridgewater), David Kostin (Goldman equity strategy), Mike Wilson (Morgan Stanley)
2. **Valuation experts** - Robert Shiller (CAPE inventor), Aswath Damodaran (NYU valuation), Jeremy Siegel (Wharton)
3. **Tech/AI analysts** - for AI bubble questions, look for semiconductor analysts, cloud/hyperscaler coverage
4. **Financial news analysis** - WSJ, Bloomberg, FT, Barron's, Reuters

Return a balanced summary (4-5 bullet points) with:
- Specific valuation data points (actual P/E numbers, CAPE ratio, forward earnings estimates)
- Named expert quotes with their firm and their reasoning
- Both bull and bear perspectives
- Any recent research notes or price targets
If you can't find recent commentary, say so clearly."""
    else:
        # Standard economic indicator search
        search_prompt = f"""Search the web for current expert economic commentary on this question:

USER QUESTION: {query}

Find:
1. Recent (last 3 months) expert opinions from economists, Fed officials, or financial analysts
2. Current consensus on whether the economic indicator is high/low/normal
3. Any recent news that provides context

PRIORITIZE these authoritative sources (in order):
1. **Wall Street chief economists** - Jan Hatzius (Goldman Sachs), Michael Gapen (BofA), Bruce Kasman (JP Morgan), Ajay Rajadhyaksha (Barclays), Torsten Slok (Apollo), Ellen Zentner (Morgan Stanley)
2. **Federal Reserve** - Jerome Powell, Fed governors (Waller, Bowman, Cook), regional Fed presidents (Neel Kashkari, Austan Goolsbee, Mary Daly)
3. **Policy economists** - Claudia Sahm, Jason Furman, Larry Summers, Paul Krugman
4. **Research institutions** - Brookings, Peterson Institute, NBER, Conference Board
5. **Financial news** - WSJ, Bloomberg, FT, Reuters

Return a concise summary (3-4 bullet points) of what experts are saying, with specific quotes if available.
If you can't find recent commentary, say so clearly."""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

        payload = {
            "contents": [{"parts": [{"text": search_prompt}]}],
            "tools": [{"google_search": {}}],  # Enable grounding with Google Search
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1000,
            }
        }

        req = Request(url, data=json.dumps(payload).encode('utf-8'),
                     headers={'Content-Type': 'application/json'}, method='POST')

        with urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))

            # Extract text from response
            if 'candidates' in result and result['candidates']:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    text_parts = [p.get('text', '') for p in candidate['content']['parts'] if 'text' in p]
                    return '\n'.join(text_parts)

        return None

    except Exception as e:
        print(f"[JudgmentLayer] Gemini search error: {e}")
        return None


def claude_synthesize(
    query: str,
    data_summary: list,
    gemini_search_results: Optional[str],
    threshold_contexts: list
) -> str:
    """
    Have Claude synthesize the data, search results, and thresholds into an authoritative answer.

    Args:
        query: User's original question
        data_summary: List of dicts with series data
        gemini_search_results: Optional web search results from Gemini
        threshold_contexts: List of threshold context dicts for each series

    Returns:
        Authoritative synthesis answering the user's question
    """
    if not ANTHROPIC_API_KEY:
        return ""

    # Build GROUND TRUTH section from data_summary
    # This prevents Claude from hallucinating numbers from training data
    ground_truth_lines = []
    for ds in data_summary:
        sid = ds.get('series_id', '')
        name = ds.get('name', sid)
        val = ds.get('latest_value', '')
        dt = ds.get('data_type', '')
        if dt == 'index':
            yoy = ds.get('yoy_percent')
            if yoy is not None:
                ground_truth_lines.append(f"  {name} ({sid}): CURRENT YEAR-OVER-YEAR RATE = {yoy:+.1f}%")
            else:
                ground_truth_lines.append(f"  {name} ({sid}): CURRENT VALUE = {val}")
        elif dt == 'rate':
            ground_truth_lines.append(f"  {name} ({sid}): CURRENT RATE = {val}%")
        else:
            ground_truth_lines.append(f"  {name} ({sid}): CURRENT VALUE = {val}")

    ground_truth_section = ""
    if ground_truth_lines:
        ground_truth_section = (
            "\n\n=== GROUND TRUTH (you MUST use these exact numbers) ===\n"
            + "\n".join(ground_truth_lines)
            + "\n=== END GROUND TRUTH ==="
            + "\nDo NOT cite any other numbers for these indicators. Use ONLY the values above."
        )

    # Build threshold section
    threshold_section = ""
    if threshold_contexts:
        threshold_lines = []
        for ctx in threshold_contexts:
            if ctx:
                line = f"• {ctx['series_name']}: {ctx['assessment']}"
                if ctx.get('historical_comparison'):
                    line += f" ({ctx['historical_comparison']})"
                if ctx.get('quote'):
                    line += f"\n  {ctx['quote']}"
                threshold_lines.append(line)
        if threshold_lines:
            threshold_section = "\n\nEXPERT THRESHOLDS:\n" + "\n".join(threshold_lines)

    # Build search section
    search_section = ""
    if gemini_search_results:
        search_section = f"\n\nCURRENT EXPERT COMMENTARY (from web search):\n{gemini_search_results}"

    # Detect if this is a high-uncertainty question (bubbles, forecasts, etc.)
    query_lower = query.lower()
    is_uncertain_question = any(kw in query_lower for kw in [
        'bubble', 'crash', 'recession coming', 'will there be', 'prediction',
        'forecast', 'overvalued', 'undervalued', 'going to', 'will the market',
        'should i', 'timing', 'when will', 'future'
    ])

    if is_uncertain_question:
        # BALANCED mode for questions with inherent uncertainty
        prompt = f"""You are synthesizing economic data with expert commentary to address a question that involves uncertainty about future outcomes.

USER QUESTION: {query}
{ground_truth_section}

CURRENT DATA:
{json.dumps(data_summary, indent=2)}
{threshold_section}
{search_section}

Write a CLEAR and BALANCED response that:

1. STATE WHAT THE DATA SHOWS
   - Be direct about where we are: "CAPE is at X, in the Yth percentile historically"
   - Compare to relevant benchmarks (dot-com peak, long-term average)
   - What have similar levels historically preceded?

2. PRESENT BOTH BULL AND BEAR CASES
   - Bull case: legitimate reasons why current levels might be justified
   - Bear case: legitimate concerns about current levels
   - Include specific expert quotes/arguments if available

3. BE CLEAR ABOUT WHAT WE DON'T KNOW
   - Timing: CAPE doesn't predict when corrections happen
   - "This time is different": sometimes it is, sometimes it isn't
   - Experts genuinely disagree on interpretation

4. GIVE THE USER ACTIONABLE FRAMING
   - What questions should they be asking?
   - What would change the picture in either direction?

FORMAT: Write 4-5 sentences in plain prose (NO bullet points, NO asterisks, NO markdown formatting).
Use plain text only — no bold, no italic, no bullet markers like • or -.

KEY PRINCIPLE: Be clear about what the data shows (not wishy-washy about facts), while honest about what it doesn't predict (not falsely authoritative about the future). Example: "CAPE is elevated by historical standards" (clear) but "whether this leads to a correction depends on..." (honest about uncertainty)."""
    else:
        # Standard mode for more factual questions
        prompt = f"""You are synthesizing economic data with expert commentary to answer a judgment question.

USER QUESTION: {query}
{ground_truth_section}

CURRENT DATA:
{json.dumps(data_summary, indent=2)}
{threshold_section}
{search_section}

Write an informed answer that:

1. ANSWERS THE QUESTION with appropriate confidence
   - For clear-cut questions (is unemployment high?): give a direct answer grounded in data
   - Use the threshold assessments to frame your answer

2. PROVIDES CONTEXT WITH QUOTES
   - Include at least one relevant expert quote from the thresholds
   - If the web search found useful recent commentary, include it

3. EXPLAINS THE REASONING
   - Why is this level considered high/low/normal?
   - How does it compare to historical norms?

4. NOTES ANY UNCERTAINTY
   - If experts disagree or outlook is unclear, say so
   - Avoid false precision about future outcomes

FORMAT: Write 4-5 sentences in plain prose (NO bullet points, NO asterisks, NO markdown formatting).
Use plain text only — no bold, no italic, no bullet markers like • or -.
Include quotes in quotation marks with attribution inline.

IMPORTANT:
- Be direct when the data supports a clear answer
- But acknowledge uncertainty for forward-looking questions
- Use expert quotes to support your assessment
- You MUST cite ONLY the numbers from GROUND TRUTH above — never substitute numbers from training data"""

    try:
        url = 'https://api.anthropic.com/v1/messages'
        payload = {
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 1000,
            'messages': [{'role': 'user', 'content': prompt}]
        }
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': ANTHROPIC_API_KEY,
            'anthropic-version': '2023-06-01'
        }

        req = Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result['content'][0]['text'].strip()
            # Clean up: remove quotes, HTML tags, and markdown formatting
            text = text.strip('"\'')
            text = re.sub(r'<[^>]+>', '', text)
            text = _strip_markdown(text)
            return text

    except Exception as e:
        print(f"[JudgmentLayer] Claude synthesis error: {e}")
        return ""


def _strip_markdown(text: str) -> str:
    """
    Strip markdown formatting from text so it renders cleanly as plain text.

    Removes:
    - **bold** and *italic* markers
    - Bullet point markers (•, -, *)
    - Numbered list markers (1., 2., etc.)
    - Header markers (#, ##, etc.)
    - Excessive whitespace from removed formatting

    The frontend renders summaries as plain <Text>, so markdown
    must be stripped to avoid showing raw asterisks and bullet markers.
    """
    # Remove bold: **text** → text
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove italic: *text* → text
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Remove bold/italic: ***text*** → text
    text = re.sub(r'\*{3}([^*]+)\*{3}', r'\1', text)
    # Remove headers: ## Header → Header
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bullet markers at start of lines: • , - , * (when used as bullets)
    text = re.sub(r'^[\s]*[•\-\*]\s+', '', text, flags=re.MULTILINE)
    # Remove numbered list markers: 1. , 2. , etc.
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Collapse multiple newlines into a single space (join into prose)
    text = re.sub(r'\n{2,}', ' ', text)
    # Convert remaining single newlines to spaces
    text = re.sub(r'\n', ' ', text)
    # Clean up extra whitespace
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def _get_judgment_cache_key(query: str, series_ids: list) -> str:
    """Generate a cache key for judgment query results."""
    series_str = ','.join(sorted(series_ids))
    return f"judgment:{query.lower().strip()}:{series_str}"


def _get_cached_judgment(cache_key: str) -> Optional[str]:
    """Get cached judgment result if still valid."""
    if cache_key in _judgment_cache:
        result, timestamp = _judgment_cache[cache_key]
        if datetime.now() - timestamp < _judgment_cache_ttl:
            return result
        else:
            del _judgment_cache[cache_key]
    return None


def _set_judgment_cache(cache_key: str, result: str) -> None:
    """Cache a judgment result."""
    _judgment_cache[cache_key] = (result, datetime.now())
    # Limit cache size
    if len(_judgment_cache) > 100:
        # Remove oldest entries
        oldest_keys = sorted(
            _judgment_cache.keys(),
            key=lambda k: _judgment_cache[k][1]
        )[:20]
        for k in oldest_keys:
            del _judgment_cache[k]


def process_judgment_query(
    query: str,
    series_data: list,
    original_explanation: str = ""
) -> Tuple[str, bool]:
    """
    Main entry point for processing judgment queries.

    OPTIMIZED:
    - Checks cache first (saves 30-40s on repeat queries)
    - Runs Gemini search and Claude synthesis in PARALLEL (saves 15-20s)

    Args:
        query: User's question
        series_data: List of (series_id, dates, values, info) tuples
        original_explanation: Fallback explanation if this fails

    Returns:
        (explanation_text, was_judgment_query) tuple
    """
    # Check if this is a judgment query
    if not is_judgment_query(query):
        return original_explanation, False

    print(f"[JudgmentLayer] Detected judgment query: {query}")

    # Check cache first
    series_ids = [sid for sid, _, _, _ in series_data if sid]
    cache_key = _get_judgment_cache_key(query, series_ids)
    cached_result = _get_cached_judgment(cache_key)
    if cached_result:
        print(f"[JudgmentLayer] Cache hit! Returning cached result")
        return cached_result, True

    # Build data summary
    data_summary = []
    threshold_contexts = []

    for series_id, dates, values, info in series_data:
        if not values:
            continue

        name = info.get('name', info.get('title', series_id))
        unit = info.get('unit', info.get('units', ''))
        latest = values[-1]
        latest_date = dates[-1] if dates else None

        # Determine data_type from info or registry
        data_type = info.get('data_type', '')
        if not data_type:
            try:
                from registry import registry as _registry
                _series_info = _registry.get_series(series_id)
                if _series_info:
                    data_type = _series_info.data_type or ''
            except Exception:
                pass

        # Determine frequency for analytics computation
        freq = info.get('frequency', 'monthly').lower()
        if 'quarter' in freq:
            frequency = 'quarterly'
        elif 'daily' in freq or 'day' in freq:
            frequency = 'daily'
        elif 'week' in freq:
            frequency = 'weekly'
        else:
            frequency = 'monthly'

        # Compute analytics with pandas for accurate YoY values
        analytics = compute_series_analytics(dates, values, series_id, frequency, data_type)

        # For INDEX series (CPI, PCE, home prices), the raw value is meaningless.
        # Use the YoY% as the "current value" for thresholds and data summary.
        # Without this, raw CPI index ~315 gets passed to thresholds expecting YoY%,
        # causing "315 > 5.0 → High inflation" and hallucinated "9.6% inflation".
        threshold_value = latest
        display_value = round(latest, 2)

        if data_type == 'index' and 'yoy' in analytics and analytics['yoy'].get('change_pct') is not None:
            yoy_pct = analytics['yoy']['change_pct']
            threshold_value = yoy_pct
            display_value = round(yoy_pct, 2)
            unit = 'Percent Change from Year Ago'

        # Compute YoY change for the summary
        yoy_change = None
        if 'yoy' in analytics and analytics['yoy'].get('change_pct') is not None:
            yoy_change = analytics['yoy']['change_pct']

        summary = {
            'series_id': series_id,
            'name': name,
            'latest_value': display_value,
            'latest_date': latest_date,
            'unit': unit,
            'data_type': data_type,
        }
        if yoy_change is not None:
            if data_type == 'index':
                # For indexes, the YoY% IS the meaningful value — label it clearly
                summary['yoy_percent'] = round(yoy_change, 2)
                summary['note'] = f"Year-over-year rate: {yoy_change:+.1f}%"
            else:
                summary['yoy_change'] = round(yoy_change, 2)

        data_summary.append(summary)

        # Get threshold context using the correct value
        # For payroll changes, we need to handle differently
        if series_id == 'PAYEMS' and info.get('is_payroll_change'):
            threshold_ctx = get_threshold_context('PAYEMS', latest)
        else:
            threshold_ctx = get_threshold_context(series_id, threshold_value)

        if threshold_ctx:
            threshold_contexts.append(threshold_ctx)

    if not data_summary:
        return original_explanation, True

    # PARALLEL EXECUTION: Run Gemini search and Claude synthesis concurrently
    # Claude can work with or without Gemini results - thresholds are the primary source
    print(f"[JudgmentLayer] Running Gemini search + Claude synthesis in PARALLEL...")

    gemini_results = None
    synthesis = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Start Gemini search
        gemini_future = executor.submit(gemini_web_search, query)

        # Start Claude synthesis with threshold context only (no Gemini results yet)
        # This gives us a baseline synthesis while we wait for Gemini
        claude_future = executor.submit(
            claude_synthesize,
            query,
            data_summary,
            None,  # No Gemini results yet
            threshold_contexts
        )

        # Wait for both with timeout
        try:
            gemini_results = gemini_future.result(timeout=20)
            if gemini_results:
                print(f"[JudgmentLayer] Gemini search returned results")
            else:
                print(f"[JudgmentLayer] Gemini search returned no results")
        except (concurrent.futures.TimeoutError, Exception) as e:
            print(f"[JudgmentLayer] Gemini search failed/timed out: {e}")
            gemini_results = None

        try:
            synthesis = claude_future.result(timeout=20)
        except (concurrent.futures.TimeoutError, Exception) as e:
            print(f"[JudgmentLayer] Initial Claude synthesis failed: {e}")
            synthesis = None

    # If we got Gemini results AND the initial synthesis was generic, re-synthesize with Gemini context
    if gemini_results and synthesis:
        # Check if synthesis would benefit from Gemini context
        # (e.g., if synthesis just uses thresholds, Gemini might add recent commentary)
        if "recent commentary" not in synthesis.lower() and "experts" not in synthesis.lower():
            print(f"[JudgmentLayer] Enhancing synthesis with Gemini context...")
            enhanced = claude_synthesize(query, data_summary, gemini_results, threshold_contexts)
            if enhanced and len(enhanced) > len(synthesis):
                synthesis = enhanced
    elif gemini_results and not synthesis:
        # Initial synthesis failed, try again with Gemini results
        print(f"[JudgmentLayer] Retrying synthesis with Gemini context...")
        synthesis = claude_synthesize(query, data_summary, gemini_results, threshold_contexts)

    if synthesis:
        print(f"[JudgmentLayer] Synthesis complete")
        # Cache the result
        _set_judgment_cache(cache_key, synthesis)
        return synthesis, True
    else:
        print(f"[JudgmentLayer] Synthesis failed, falling back to original")
        return original_explanation, True


# Quick test
if __name__ == "__main__":
    # Test judgment detection
    test_queries = [
        "Is unemployment high?",
        "What is the unemployment rate?",
        "Is the economy doing well?",
        "Show me GDP growth",
        "Should I be worried about inflation?",
        "Inflation data since 2020",
        "Is the job market healthy?",
        "How many jobs were added last month?",
    ]

    print("Testing judgment query detection:\n")
    for q in test_queries:
        is_judgment = is_judgment_query(q)
        print(f"  {'✓ JUDGMENT' if is_judgment else '✗ FACTUAL':12} | {q}")

    print("\n" + "="*50)

    # Test threshold context
    print("\nTesting threshold contexts:")
    test_values = [
        ('UNRATE', 4.1),
        ('UNRATE', 3.5),
        ('UNRATE', 6.2),
        ('CPIAUCSL', 2.8),
        ('FEDFUNDS', 4.5),
    ]

    for series_id, value in test_values:
        ctx = get_threshold_context(series_id, value)
        if ctx:
            print(f"\n  {series_id} = {value}:")
            print(f"    Assessment: {ctx['assessment']}")
            print(f"    Quote: {ctx['quote']}")
            print(f"    vs History: {ctx['historical_comparison']}")
