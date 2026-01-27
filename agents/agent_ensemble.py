#!/usr/bin/env python3
"""
Ensemble query plan generation using multiple LLMs.

Architecture:
1. Claude (Sonnet) generates a query plan
2. Gemini generates a parallel query plan
3. GPT-4 judges both plans blindly and merges the best aspects

This approach leverages the strengths of each model to produce
higher-quality query plans than any single model alone.
"""

import json
import os
import time
import concurrent.futures
from pathlib import Path
from urllib.request import urlopen, Request
from typing import Optional, Dict, Any, Tuple

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Look for .env in parent directory (project root)
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, rely on system env vars

# API Keys - loaded from environment variables
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def call_claude(prompt: str, retries: int = 3) -> Optional[Dict]:
    """
    Call Claude Sonnet to generate a query plan.

    Args:
        prompt: The full prompt including expert context and user query
        retries: Number of retry attempts on failure

    Returns:
        Parsed JSON query plan or None on failure
    """
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

    for attempt in range(retries):
        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'),
                         headers=headers, method='POST')
            with urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                content = result['content'][0]['text']
                return _extract_json(content)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  Claude ERROR after {retries} attempts: {e}")
                return None
    return None


def call_gemini(prompt: str, retries: int = 3) -> Optional[Dict]:
    """
    Call Google Gemini to generate a query plan.

    Args:
        prompt: The full prompt including expert context and user query
        retries: Number of retry attempts on failure

    Returns:
        Parsed JSON query plan or None on failure
    """
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0.7,
            'maxOutputTokens': 1000
        }
    }
    headers = {
        'Content-Type': 'application/json'
    }

    for attempt in range(retries):
        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'),
                         headers=headers, method='POST')
            with urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                content = result['candidates'][0]['content']['parts'][0]['text']
                return _extract_json(content)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  Gemini ERROR after {retries} attempts: {e}")
                return None
    return None


def call_gpt(prompt: str, retries: int = 3) -> Optional[str]:
    """
    Call GPT-4 to judge and merge query plans.

    Args:
        prompt: The judging prompt with both plans
        retries: Number of retry attempts on failure

    Returns:
        GPT's response text or None on failure
    """
    url = 'https://api.openai.com/v1/chat/completions'
    payload = {
        'model': 'gpt-4o',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 1500,
        'temperature': 0.3  # Lower temperature for more consistent judging
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENAI_API_KEY}'
    }

    for attempt in range(retries):
        try:
            req = Request(url, data=json.dumps(payload).encode('utf-8'),
                         headers=headers, method='POST')
            with urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result['choices'][0]['message']['content']
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  GPT ERROR after {retries} attempts: {e}")
                return None
    return None


def _extract_json(content: str) -> Optional[Dict]:
    """
    Extract JSON from LLM response, handling markdown code blocks.

    Args:
        content: Raw LLM response text

    Returns:
        Parsed JSON dict or None if parsing fails
    """
    try:
        # Try to extract from markdown code blocks
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        return json.loads(content.strip())
    except json.JSONDecodeError:
        # Try parsing the whole content as JSON
        try:
            return json.loads(content.strip())
        except:
            return None


def generate_ensemble_plan(
    user_query: str,
    expert_prompt: str,
    verbose: bool = True
) -> Tuple[Dict, Dict]:
    """
    Generate a query plan using the ensemble approach.

    This function:
    1. Calls Claude and Gemini in parallel with the same prompt
    2. Sends both plans (anonymized as Plan A/B) to GPT-4 for judgment
    3. Returns the final merged plan along with judgment metadata

    Args:
        user_query: The user's economic data query
        expert_prompt: Domain-specific expert prompt for the agent
        verbose: Whether to print progress updates

    Returns:
        Tuple of (final_plan, judgment_metadata)
    """
    # Build the full prompt
    full_prompt = expert_prompt + MULTI_CHART_GUIDANCE + f"\n\nUSER QUERY: {user_query}"

    if verbose:
        print(f"  Generating parallel plans...")

    # Generate plans in parallel (with timeout to prevent hanging)
    LLM_TIMEOUT = 45  # seconds
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claude_future = executor.submit(call_claude, full_prompt)
        gemini_future = executor.submit(call_gemini, full_prompt)

        try:
            claude_plan = claude_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            claude_plan = None
            if verbose:
                print(f"    Claude timed out or failed: {e}")

        try:
            gemini_plan = gemini_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            gemini_plan = None
            if verbose:
                print(f"    Gemini timed out or failed: {e}")

    if verbose:
        print(f"    Claude: {claude_plan.get('series', []) if claude_plan else 'FAILED'}")
        print(f"    Gemini: {gemini_plan.get('series', []) if gemini_plan else 'FAILED'}")

    # Handle failures - fall back to whichever succeeded
    if not claude_plan and not gemini_plan:
        return None, {'error': 'Both models failed'}
    if not claude_plan:
        return gemini_plan, {'winner': 'gemini', 'reason': 'Claude failed'}
    if not gemini_plan:
        return claude_plan, {'winner': 'claude', 'reason': 'Gemini failed'}

    # Both succeeded - have GPT judge
    if verbose:
        print(f"  GPT judging plans...")

    judgment = judge_plans(user_query, claude_plan, gemini_plan)

    if not judgment:
        # Fallback to Claude if judging fails
        return claude_plan, {'winner': 'claude', 'reason': 'GPT judging failed, defaulting to Claude'}

    if verbose:
        print(f"    Winner: {judgment.get('winner', 'merged')}")

    return judgment.get('final_plan', claude_plan), judgment


def judge_plans(
    user_query: str,
    plan_a: Dict,
    plan_b: Dict
) -> Optional[Dict]:
    """
    Have GPT-4 judge two query plans and merge the best aspects.

    Plans are presented anonymously as Plan A and Plan B to avoid bias.
    GPT determines which is better overall and what each got right,
    then produces a merged final plan.

    Args:
        user_query: Original user query for context
        plan_a: First query plan (Claude)
        plan_b: Second query plan (Gemini)

    Returns:
        Dict with winner, reasoning, and final merged plan
    """
    judge_prompt = f"""You are an expert economist evaluating two query plans for retrieving Federal Reserve (FRED) economic data.

USER QUERY: "{user_query}"

PLAN A:
{json.dumps(plan_a, indent=2)}

PLAN B:
{json.dumps(plan_b, indent=2)}

## CRITICAL EVALUATION PRINCIPLE: MULTI-DIMENSIONAL ANSWERS

For any "how is X doing?" query, a good plan should cover MULTIPLE DIMENSIONS of the topic:

- **Industry/Sector health**: employment + prices + wages + output/sales
- **Overall economy**: GDP + jobs + inflation + rates
- **Demographic group**: employment rate + unemployment + participation + wages
- **Housing market**: prices + sales + starts + affordability + rates
- **Labor market**: payrolls + unemployment + job openings + wages

A plan that only returns ONE dimension (e.g., just prices for "how are restaurants doing?") is INCOMPLETE and should be penalized heavily.

Evaluate both plans based on:
1. **Multi-Dimensional Coverage**: Does the plan cover multiple relevant aspects of the topic? (MOST IMPORTANT)
2. **Series Selection**: Are the FRED series IDs correct and relevant?
3. **Completeness**: Does it tell the full story without being redundant?
4. **Explanation Quality**: Is the explanation accurate and helpful?
5. **Configuration**: Are show_yoy and combine_chart set appropriately?

Respond with JSON in this exact format:
```json
{{
    "winner": "A" or "B" or "tie",
    "plan_a_strengths": ["strength 1", "strength 2"],
    "plan_a_weaknesses": ["weakness 1"],
    "plan_b_strengths": ["strength 1", "strength 2"],
    "plan_b_weaknesses": ["weakness 1"],
    "reasoning": "Brief explanation of the decision",
    "final_plan": {{
        "series": ["SERIES1", "SERIES2"],
        "show_yoy": true/false,
        "combine_chart": true/false,
        "explanation": "Merged explanation taking the best from both plans"
    }}
}}
```

The final_plan should combine the best aspects of both plans. If one plan is clearly superior, use it as the base. If both have unique strengths, merge them intelligently."""

    response = call_gpt(judge_prompt)
    if not response:
        return None

    result = _extract_json(response)
    if result:
        # Add source tracking
        result['plan_a_source'] = 'claude'
        result['plan_b_source'] = 'gemini'
    return result


# Guidance for comprehensive responses (imported from agent_base)
MULTI_CHART_GUIDANCE = """

## CRITICAL: MULTI-DIMENSIONAL ANSWERS

The key principle: Any "how is X doing?" question requires MULTIPLE DIMENSIONS, not just one metric.

Think like an economist writing a briefing - you wouldn't answer "how is the economy doing?" with just GDP, or "how are restaurants doing?" with just prices.

### Dimension Templates by Query Type:

**Industry/Sector** ("how is [industry] doing?"):
- Employment (sector jobs)
- Prices (relevant CPI component)
- Wages/Earnings (sector pay)
- Output/Sales (production, revenue)

**Overall Economy** ("how is the economy?"):
- Growth (GDP)
- Labor (jobs, unemployment)
- Prices (inflation)
- Rates (Fed policy)

**Demographic Group** ("how are [group] doing?"):
- Employment rate (group-specific, NOT overall)
- Unemployment rate (group-specific, NOT overall)
- Labor force participation (group-specific)
- Wages/Earnings (group-specific if available)
- NEVER use aggregate series like GDP, UNRATE, PAYEMS for demographic queries

**Housing Market**:
- Prices (Case-Shiller)
- Activity (sales, starts)
- Affordability (mortgage rates, price-to-income)

**Labor Market**:
- Job gains (payrolls)
- Slack (unemployment, U6)
- Demand (job openings)
- Wages (earnings)

### Examples:
- "How are restaurants doing?" → USLAH (jobs) + CUSR0000SEFV (prices) + search for earnings
- "How is manufacturing doing?" → MANEMP (jobs) + INDPRO (output) + manufacturing earnings
- "How are women doing?" → Women's employment rate + unemployment + participation + wages

### Anti-Pattern:
NEVER return just one dimension. A single metric is an INCOMPLETE answer.

### CRITICAL RULES:

**DO NOT HALLUCINATE DATES!** Only reference dates that come from actual data. If unsure, say "recent" or "latest available".

**PAYROLLS = CHANGES, NOT LEVELS!** For employment data:
- BAD explanation: "Total nonfarm payrolls are 159.5 million"
- GOOD explanation: "The economy added 150K jobs last month, averaging 180K over 3 months"
- Always focus on job GROWTH and CHANGES - the level is almost meaningless

The explanation field should briefly describe what EACH series measures and why it's included.
"""


def process_prompts_ensemble(
    prompts: list,
    expert_prompt: str,
    output_file: str,
    category: str
) -> Dict:
    """
    Process a list of prompts using the ensemble approach.

    This is the ensemble equivalent of agent_base.process_prompts().

    Args:
        prompts: List of user queries to process
        expert_prompt: Domain-specific expert prompt
        output_file: Path to save the resulting plans JSON
        category: Category name for logging

    Returns:
        Dict mapping prompts to their query plans
    """
    print(f"\n{'='*60}")
    print(f"ENSEMBLE AGENT: {category.upper()}")
    print(f"{'='*60}")
    print(f"Processing {len(prompts)} prompts with Claude + Gemini + GPT...")

    plans = {}
    judgments = {}
    errors = []

    for i, prompt in enumerate(prompts):
        print(f"\n[{i+1}/{len(prompts)}] '{prompt}'")

        plan, judgment = generate_ensemble_plan(prompt, expert_prompt)

        if plan and plan.get('series'):
            plans[prompt] = {
                'series': plan.get('series', []),
                'show_yoy': plan.get('show_yoy', False),
                'combine_chart': plan.get('combine_chart', False),
                'explanation': plan.get('explanation', ''),
            }
            judgments[prompt] = judgment
            print(f"  -> FINAL: {plan.get('series', [])}")
        else:
            errors.append(prompt)
            print(f"  -> FAILED")

        time.sleep(0.5)  # Rate limiting

    # Save results
    with open(output_file, 'w') as f:
        json.dump(plans, f, indent=2)

    # Save judgment metadata separately
    judgment_file = output_file.replace('.json', '_judgments.json')
    with open(judgment_file, 'w') as f:
        json.dump(judgments, f, indent=2)

    print(f"\n{category} COMPLETE: {len(plans)} plans, {len(errors)} errors")
    print(f"Plans saved to: {output_file}")
    print(f"Judgments saved to: {judgment_file}")

    return plans


# ============================================================================
# APP INTEGRATION
# Functions for integrating ensemble into the main EconStats app
# ============================================================================

def load_few_shot_examples(plans_dir: Optional[str] = None, num_examples: int = 5) -> str:
    """
    Load example query plans to use as few-shot examples.

    This helps the models understand the expected format and quality
    by showing them real examples from pre-computed plans.

    Args:
        plans_dir: Directory containing plan JSON files
        num_examples: Number of examples to include

    Returns:
        Formatted string of few-shot examples
    """
    if plans_dir is None:
        plans_dir = Path(__file__).parent

    examples = []

    # Load examples from various plan files
    plan_files = [
        'plans_inflation.json',
        'plans_employment.json',
        'plans_gdp.json',
        'plans_housing.json',
        'plans_fed_rates.json'
    ]

    for plan_file in plan_files:
        plan_path = plans_dir / plan_file
        if plan_path.exists():
            try:
                with open(plan_path) as f:
                    plans = json.load(f)
                    # Get first example from each file
                    for query, plan in list(plans.items())[:1]:
                        examples.append({
                            'query': query,
                            'plan': plan
                        })
                        if len(examples) >= num_examples:
                            break
            except:
                continue
        if len(examples) >= num_examples:
            break

    if not examples:
        return ""

    # Format as few-shot examples
    examples_text = "\n\n## EXAMPLES OF GOOD QUERY PLANS\n"
    examples_text += "Here are examples of well-structured query plans:\n\n"

    for i, ex in enumerate(examples, 1):
        examples_text += f"**Example {i}: \"{ex['query']}\"**\n"
        examples_text += f"```json\n{json.dumps(ex['plan'], indent=2)}\n```\n\n"

    return examples_text


def call_ensemble_for_app(
    query: str,
    economist_prompt: str,
    previous_context: Optional[Dict] = None,
    use_few_shot: bool = True,
    verbose: bool = False
) -> Dict:
    """
    Ensemble query plan generation for the main EconStats app.

    This function integrates with app.py to provide higher-quality
    query plans for queries not found in pre-computed plans.

    Args:
        query: The user's economic data question
        economist_prompt: The full economist prompt from app.py
        previous_context: Optional context from previous queries
        use_few_shot: Whether to include few-shot examples
        verbose: Whether to print progress

    Returns:
        Dict in the format expected by app.py:
        {
            'series': [...],
            'search_terms': [...],
            'explanation': '...',
            'show_yoy': bool,
            'show_mom': bool,
            'show_avg_annual': bool,
            'combine_chart': bool,
            'is_followup': bool,
            'add_to_previous': bool,
            'keep_previous_series': bool
        }
    """
    # Default response format for app.py
    default_response = {
        'series': [],
        'search_terms': [query],
        'explanation': '',
        'show_yoy': False,
        'show_mom': False,
        'show_avg_annual': False,
        'combine_chart': False,
        'is_followup': False,
        'add_to_previous': False,
        'keep_previous_series': False
    }

    # Build the prompt with few-shot examples
    full_prompt = economist_prompt
    if use_few_shot:
        few_shot = load_few_shot_examples()
        if few_shot:
            full_prompt += few_shot

    full_prompt += f"\n\nUSER QUERY: {query}"

    # Handle follow-up context
    if previous_context and previous_context.get('series'):
        context_text = f"""

PREVIOUS CONTEXT:
- Previous query: {previous_context.get('query', '')}
- Previous series: {previous_context.get('series', [])}
- Series names: {previous_context.get('series_names', [])}

Consider whether this is a follow-up question that should modify or add to the previous data.
"""
        full_prompt += context_text

    if verbose:
        print(f"Generating ensemble plan for: {query}")

    # Generate plans in parallel (with timeout to prevent hanging)
    LLM_TIMEOUT = 45  # seconds
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claude_future = executor.submit(call_claude, full_prompt)
        gemini_future = executor.submit(call_gemini, full_prompt)

        try:
            claude_plan = claude_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            claude_plan = None
            if verbose:
                print(f"  Claude timed out or failed: {e}")

        try:
            gemini_plan = gemini_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            gemini_plan = None
            if verbose:
                print(f"  Gemini timed out or failed: {e}")

    if verbose:
        print(f"  Claude: {claude_plan.get('series', []) if claude_plan else 'FAILED'}")
        print(f"  Gemini: {gemini_plan.get('series', []) if gemini_plan else 'FAILED'}")

    # Handle failures
    if not claude_plan and not gemini_plan:
        return default_response

    if not claude_plan:
        return _normalize_plan_for_app(gemini_plan, default_response)

    if not gemini_plan:
        return _normalize_plan_for_app(claude_plan, default_response)

    # Both succeeded - have GPT judge
    if verbose:
        print(f"  GPT judging plans...")

    judgment = judge_plans(query, claude_plan, gemini_plan)

    if not judgment or not judgment.get('final_plan'):
        # Fallback to Claude if judging fails
        return _normalize_plan_for_app(claude_plan, default_response)

    final_plan = judgment.get('final_plan', claude_plan)

    if verbose:
        print(f"  Final: {final_plan.get('series', [])}")
        print(f"  Winner: {judgment.get('winner', 'merged')}")

    result = _normalize_plan_for_app(final_plan, default_response)

    # Add ensemble metadata
    result['ensemble_metadata'] = {
        'winner': judgment.get('winner'),
        'reasoning': judgment.get('reasoning'),
        'claude_series': claude_plan.get('series', []),
        'gemini_series': gemini_plan.get('series', [])
    }

    return result


def _normalize_plan_for_app(plan: Dict, default: Dict) -> Dict:
    """
    Normalize a query plan to match app.py's expected format.

    Args:
        plan: The raw plan from an LLM
        default: Default response dict

    Returns:
        Normalized plan dict
    """
    result = default.copy()

    # Map plan fields to app fields
    result['series'] = plan.get('series', [])
    result['explanation'] = plan.get('explanation', '')
    result['show_yoy'] = plan.get('show_yoy', False)
    result['combine_chart'] = plan.get('combine_chart', False)

    # Handle additional fields if present
    result['show_mom'] = plan.get('show_mom', False)
    result['show_avg_annual'] = plan.get('show_avg_annual', False)
    result['search_terms'] = plan.get('search_terms', [])
    result['is_followup'] = plan.get('is_followup', False)
    result['add_to_previous'] = plan.get('add_to_previous', False)
    result['keep_previous_series'] = plan.get('keep_previous_series', False)

    return result


# ============================================================================
# ENSEMBLE DESCRIPTION/NARRATIVE GENERATION
# Uses Claude + Gemini + GPT to generate better explanations
# ============================================================================

def generate_ensemble_description(
    query: str,
    data_summary: list,
    original_explanation: str = "",
    verbose: bool = False
) -> str:
    """
    Generate an improved description/narrative using the ensemble approach.

    This function:
    1. Calls Claude and Gemini in parallel with the data summary
    2. Has GPT-4 judge both explanations and merge the best aspects
    3. Returns the final improved explanation

    Args:
        query: The user's original question
        data_summary: List of dicts with series data (name, latest_value, yoy_change, etc.)
        original_explanation: Initial explanation to improve upon
        verbose: Whether to print progress

    Returns:
        Improved explanation string
    """
    if not data_summary:
        return original_explanation

    # Build the prompt for generating descriptions
    description_prompt = f"""You are an expert economist writing a clear, insightful summary for a user.

USER QUERY: {query}

DATA SUMMARY:
{json.dumps(data_summary, indent=2)}

INITIAL EXPLANATION: {original_explanation if original_explanation else "None provided"}

Write an improved explanation that:
1. States current values clearly with proper formatting (if unit is "Thousands", convert to millions - e.g., 159500 thousands = 159.5 million)
2. Provides meaningful context (high/low historically? trending up/down?)
3. Answers the user's actual question directly
4. Avoids jargon - write for a general audience
5. Be fact-based. Characterize as "strong", "weak", "cooling", etc. only if data supports it
6. If multiple series are shown, explain what EACH measures and why it matters

***CRITICAL - LEAD WITH THE HEADLINE SERIES!***
- UNRATE (U-3) is THE unemployment rate - lead with this, not U6RATE
- CPIAUCSL (headline CPI) is THE inflation rate - lead with this, not core
- PAYEMS is THE jobs number - lead with this
- The first series listed is typically the "headline" that users expect to see first
- Secondary/broader measures (U-6, core inflation, etc.) should come AFTER the headline

***CRITICAL - DO NOT HALLUCINATE DATES!***
- ONLY use dates that appear in the DATA SUMMARY above
- If you don't see a specific date in the data, say "recent data" or "latest available"
- NEVER guess or make up dates like "December 2024" unless that exact date is in the data

***CRITICAL - PAYROLLS = CHANGES, NOT LEVELS!***
- For employment/payroll data, ALWAYS focus on job GROWTH and CHANGES
- BAD: "Total nonfarm payrolls stand at 159.5 million"
- GOOD: "The economy added 150,000 jobs last month, with a 3-month average of 180,000"
- The absolute LEVEL of employment is almost meaningless - CHANGES tell the story
- Mention: monthly gains, 3-month averages, year-over-year job gains

CRITICAL: Do NOT start with "The data shows..." or "Looking at...". Answer directly.

Keep it to 4-6 concise sentences. Return only the explanation text, nothing else."""

    if verbose:
        print(f"  Generating ensemble description...")

    # Generate descriptions in parallel (with timeout to prevent hanging)
    LLM_TIMEOUT = 45  # seconds
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claude_future = executor.submit(_generate_description_claude, description_prompt)
        gemini_future = executor.submit(_generate_description_gemini, description_prompt)

        try:
            claude_desc = claude_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            claude_desc = None
            if verbose:
                print(f"    Claude desc timed out or failed: {e}")

        try:
            gemini_desc = gemini_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            gemini_desc = None
            if verbose:
                print(f"    Gemini desc timed out or failed: {e}")

    if verbose:
        print(f"    Claude: {'OK' if claude_desc else 'FAILED'}")
        print(f"    Gemini: {'OK' if gemini_desc else 'FAILED'}")

    # Handle failures
    if not claude_desc and not gemini_desc:
        return original_explanation
    if not claude_desc:
        return gemini_desc
    if not gemini_desc:
        return claude_desc

    # Both succeeded - have GPT judge and merge
    if verbose:
        print(f"  GPT judging descriptions...")

    final_desc = _judge_descriptions(query, data_summary, claude_desc, gemini_desc)

    if verbose:
        print(f"    Final: {'OK' if final_desc else 'FAILED'}")

    return final_desc if final_desc else claude_desc


def _generate_description_claude(prompt: str) -> Optional[str]:
    """Generate description using Claude."""
    url = 'https://api.anthropic.com/v1/messages'
    payload = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 400,
        'messages': [{'role': 'user', 'content': prompt}]
    }
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01'
    }

    try:
        req = Request(url, data=json.dumps(payload).encode('utf-8'),
                     headers=headers, method='POST')
        with urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result['content'][0]['text'].strip().strip('"\'')
            # Strip any HTML tags LLM might have generated
            import re
            text = re.sub(r'<[^>]+>', '', text)
            return text
    except Exception as e:
        return None


def _generate_description_gemini(prompt: str) -> Optional[str]:
    """Generate description using Gemini."""
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0.7,
            'maxOutputTokens': 400
        }
    }
    headers = {
        'Content-Type': 'application/json'
    }

    try:
        req = Request(url, data=json.dumps(payload).encode('utf-8'),
                     headers=headers, method='POST')
        with urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result['candidates'][0]['content']['parts'][0]['text'].strip().strip('"\'')
            # Strip any HTML tags LLM might have generated
            import re
            text = re.sub(r'<[^>]+>', '', text)
            return text
    except Exception as e:
        return None


def _judge_descriptions(
    query: str,
    data_summary: list,
    desc_a: str,
    desc_b: str
) -> Optional[str]:
    """Have GPT-4 judge two descriptions and produce the best merged version."""
    judge_prompt = f"""You are an expert economist and editor evaluating two explanations of economic data.

USER QUERY: "{query}"

DATA CONTEXT:
{json.dumps(data_summary, indent=2)}

EXPLANATION A:
{desc_a}

EXPLANATION B:
{desc_b}

Evaluate both explanations on:
1. **Accuracy**: Are the numbers and dates correct?
2. **Clarity**: Is it easy to understand for a general audience?
3. **Completeness**: Does it address all the data shown, not just one series?
4. **Insight**: Does it provide meaningful context (trends, comparisons, implications)?
5. **Directness**: Does it answer the question without preamble?

Write the BEST possible explanation by:
- Using the most accurate facts from either explanation
- Combining the best insights from both
- Maintaining a clear, direct style
- Ensuring all series are addressed if multiple are shown

Return ONLY the final improved explanation text. No commentary or meta-discussion."""

    response = call_gpt(judge_prompt)
    if response:
        text = response.strip().strip('"\'')
        # Strip any HTML tags LLM might have generated
        import re
        text = re.sub(r'<[^>]+>', '', text)
        return text
    return None


# ============================================================================
# DIMENSION DISCOVERY: Ask LLMs what topics are missing, then search FRED
# ============================================================================

def suggest_missing_dimensions(
    query: str,
    existing_series_names: list,
    verbose: bool = False
) -> Dict:
    """
    Ask LLMs what DIMENSIONS/TOPICS are missing to fully answer a query.

    IMPORTANT: This returns SEARCH TERMS, not series IDs. LLMs hallucinate
    series IDs, but they're good at identifying what topics are missing.
    The caller should use FRED search API to find actual series.

    Args:
        query: The user's original question
        existing_series_names: Names of series already in the plan (not IDs)
        verbose: Whether to print progress

    Returns:
        Dict with:
        - missing_dimensions: List of topic descriptions
        - search_terms: List of FRED search terms to find those dimensions
    """
    if verbose:
        print(f"  Finding missing dimensions for: {query}")
        print(f"  Already have: {existing_series_names}")

    dimension_prompt = f"""You are an expert economist. A user asked: "{query}"

We already have data on: {existing_series_names if existing_series_names else "Nothing yet"}

## YOUR TASK
Identify what ADDITIONAL DIMENSIONS are needed to fully answer this question.

Think like an economist writing a comprehensive briefing:
- Industry health needs: employment + prices + wages + output/sales
- Economy health needs: GDP + jobs + inflation + rates
- Demographic questions need: group-specific employment, unemployment, participation, wages
- Housing needs: prices + sales + starts + affordability

## CRITICAL RULES
1. Return SEARCH TERMS for FRED, not series IDs (you don't know the exact IDs)
2. Be SPECIFIC to the query topic (for restaurants, search "restaurant employment" not "total employment")
3. Only suggest dimensions we DON'T already have
4. Suggest 1-3 additional dimensions maximum

## RESPONSE FORMAT
Return JSON only:
```json
{{
    "missing_dimensions": ["dimension 1 description", "dimension 2 description"],
    "search_terms": ["specific FRED search term 1", "specific FRED search term 2"]
}}
```

Example for "How are restaurants doing?" with existing price data:
```json
{{
    "missing_dimensions": ["restaurant/food service employment", "restaurant worker wages"],
    "search_terms": ["food services employment", "leisure hospitality earnings"]
}}
```

If the existing data already covers the question well, return empty lists."""

    # Generate suggestions in parallel from Claude and Gemini (with timeout)
    LLM_TIMEOUT = 45  # seconds
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claude_future = executor.submit(call_claude, dimension_prompt)
        gemini_future = executor.submit(call_gemini, dimension_prompt)

        try:
            claude_result = claude_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            claude_result = None
            if verbose:
                print(f"    Claude dimension timed out or failed: {e}")

        try:
            gemini_result = gemini_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            gemini_result = None
            if verbose:
                print(f"    Gemini dimension timed out or failed: {e}")

    if verbose:
        print(f"    Claude: {claude_result.get('search_terms', []) if claude_result else 'FAILED'}")
        print(f"    Gemini: {gemini_result.get('search_terms', []) if gemini_result else 'FAILED'}")

    # Merge results - combine unique search terms from both
    all_search_terms = set()
    all_dimensions = set()

    if claude_result:
        all_search_terms.update(claude_result.get('search_terms', []))
        all_dimensions.update(claude_result.get('missing_dimensions', []))

    if gemini_result:
        all_search_terms.update(gemini_result.get('search_terms', []))
        all_dimensions.update(gemini_result.get('missing_dimensions', []))

    # Limit to 3 search terms to avoid overloading
    search_terms = list(all_search_terms)[:3]

    return {
        'missing_dimensions': list(all_dimensions),
        'search_terms': search_terms,
        'claude_suggestion': claude_result,
        'gemini_suggestion': gemini_result
    }


def validate_series_relevance(
    query: str,
    series_list: list,
    verbose: bool = False
) -> Dict:
    """
    Validate that each series in the list is relevant and adds value to answering the query.

    Uses GPT to review series and filter out:
    - Irrelevant series (don't relate to the query topic)
    - Overly broad series (e.g., "All Corporations" for a specific industry question)
    - Redundant series (duplicate information)

    Args:
        query: The user's original question
        series_list: List of dicts with 'id', 'title', and optionally 'description'
        verbose: Whether to print progress

    Returns:
        Dict with:
        - valid_series: List of series IDs that passed validation
        - rejected_series: List of rejected series with reasons
        - validation_reasoning: Overall explanation
    """
    if not series_list:
        return {'valid_series': [], 'rejected_series': [], 'validation_reasoning': 'No series to validate'}

    if verbose:
        print(f"  Validating {len(series_list)} series for: {query}")

    # Format series for the prompt
    series_desc = "\n".join([
        f"- {s.get('id', 'Unknown')}: {s.get('title', 'No title')}"
        for s in series_list
    ])

    validation_prompt = f"""You are a STRICT economist validating data series for a user query.

USER QUERY: "{query}"

PROPOSED SERIES:
{series_desc}

## STRICT REJECTION RULES

### DEMOGRAPHIC QUERIES (about women, Black workers, Hispanic, immigrants, etc.)
- **REJECT any series for a DIFFERENT demographic group**
- "Black workers" query MUST NOT include women's employment/unemployment data
- "Women" query MUST NOT include Black/Hispanic/immigrant data
- Only accept series SPECIFICALLY for the demographic mentioned in the query

### INDUSTRY QUERIES (about restaurants, trucking, food trucks, solar, etc.)
- **REJECT generic "All Industries" or "Manufacturing" for specific industry queries**
- **REJECT demographic data** (women's employment, etc.) for industry queries
- Only accept industry-SPECIFIC series or DIRECT proxies (e.g., "Food Services" for restaurants)

### GEOGRAPHIC QUERIES (about Texas, California, specific states/regions)
- **REJECT national data** if query asks about a specific state/region
- Flag when no state-level data is available

### GENERAL REJECTION RULES
1. **Irrelevant**: Don't relate to the query topic
2. **Overly broad**: Too general to be useful
3. **Wrong scope**: Wrong demographic, geography, or industry
4. **Redundant**: Duplicates information
5. **Historical only**: No recent data

## CRITICAL: When NO series are relevant
If NONE of the proposed series actually answer the query, return an EMPTY valid_series list.
It is BETTER to return no data than to return WRONG data.

### OUT-OF-SCOPE QUERIES
Many questions are OUTSIDE what FRED economic data covers. Examples:
- "What's the average retirement age?" → FRED doesn't have this
- "What's the population of Texas?" → Not economic data
- "Who is the Fed chair?" → Not a data series
- "What's the weather?" → Completely unrelated

If the query asks for something FRED doesn't track, REJECT ALL SERIES.
Do NOT show inflation/GDP/jobs data for non-economic questions!

## RESPONSE FORMAT
Return JSON only:
```json
{{
    "valid_series": ["SERIES_ID_1", "SERIES_ID_2"],
    "rejected_series": [
        {{"id": "SERIES_ID_3", "reason": "Wrong demographic - women's data for Black workers query"}}
    ],
    "validation_reasoning": "Brief explanation of the filtering decisions"
}}
```

Be VERY STRICT. When in doubt, REJECT."""

    # Use GPT for validation (it's good at this kind of judgment)
    response = call_gpt(validation_prompt)

    if not response:
        # GPT unavailable - trust the input series rather than rejecting everything
        # Pre-computed plans are curated and don't need validation
        if verbose:
            print("    Validation unavailable - trusting input series")
        return {
            'valid_series': [s.get('id') for s in series_list],
            'rejected_series': [],
            'validation_reasoning': 'Validation unavailable - using pre-computed plan as-is',
            'validation_skipped': True
        }

    result = _extract_json(response)

    if not result:
        # Parse failed - trust the input series rather than rejecting everything
        if verbose:
            print("    Validation parse failed - trusting input series")
        return {
            'valid_series': [s.get('id') for s in series_list],
            'rejected_series': [],
            'validation_reasoning': 'Could not parse validation response - using plan as-is',
            'validation_skipped': True
        }

    if verbose:
        print(f"    Valid: {result.get('valid_series', [])}")
        print(f"    Rejected: {[r.get('id') for r in result.get('rejected_series', [])]}")

    return result


# ============================================================================
# AUGMENTATION: Enhance pre-computed plans with missing dimensions (DEPRECATED)
# Use suggest_missing_dimensions + FRED search instead
# ============================================================================

def augment_query_plan(
    query: str,
    existing_series: list,
    existing_explanation: str = "",
    verbose: bool = False
) -> Dict:
    """
    Augment a pre-computed query plan with missing dimensions.

    Uses ensemble approach: Claude and Gemini suggest additions in parallel,
    GPT judges and merges the best suggestions.

    Args:
        query: The user's original question
        existing_series: Series IDs already in the pre-computed plan
        existing_explanation: Explanation from pre-computed plan
        verbose: Whether to print progress

    Returns:
        Dict with:
        - additional_series: List of new series to add
        - combined_series: Original + new series
        - augmented_explanation: Updated explanation
        - augmentation_metadata: Details about what was added and why
    """
    if verbose:
        print(f"  Augmenting plan for: {query}")
        print(f"  Existing series: {existing_series}")

    augment_prompt = f"""You are an expert economist reviewing a query plan for FRED economic data.

USER QUERY: "{query}"

CURRENT PLAN has these series: {existing_series}
Current explanation: {existing_explanation if existing_explanation else "None"}

## YOUR TASK: Identify what dimensions are MISSING

For comprehensive answers, queries need MULTIPLE DIMENSIONS:

**Industry/Sector** ("how is [industry] doing?") needs:
- Employment (sector jobs)
- Prices (relevant CPI component)
- Wages/Earnings (sector pay)
- Output/Sales (production, revenue)

**Overall Economy** ("how is the economy?") needs:
- Growth (GDP)
- Labor (jobs, unemployment)
- Prices (inflation)
- Rates (Fed policy)

**Demographic Group** ("how are [group] doing?") needs:
- Employment rate (group-specific, NOT overall)
- Unemployment rate (group-specific, NOT overall)
- Labor force participation (group-specific)
- Wages/Earnings (group-specific if available)

**Housing Market** needs:
- Prices (Case-Shiller)
- Activity (sales, starts)
- Affordability (mortgage rates)

## WELL-KNOWN FRED SERIES BY CATEGORY:

Employment by Industry:
- USLAH = Leisure & hospitality employment (includes restaurants)
- MANEMP = Manufacturing employment
- CES4300000001 = Retail trade employment
- USCONS = Construction employment
- USFIRE = Finance/insurance employment
- USINFO = Information sector employment
- USPBS = Professional/business services

Prices by Category:
- CUSR0000SEFV = Food away from home (restaurant prices)
- CUSR0000SAH1 = Shelter prices
- CUSR0000SETB01 = Gasoline prices
- CPIMEDSL = Medical care prices
- CUSR0000SEEB = Tuition prices

Wages/Earnings:
- CES7000000003 = Leisure/hospitality hourly earnings
- CES3000000003 = Manufacturing hourly earnings
- CES0500000003 = Private sector avg hourly earnings

Demographics (Foreign-born):
- LNU02073395 = Foreign-born unemployment rate
- LNU02073413 = Foreign-born employed
- LNU01073413 = Foreign-born labor force

Demographics (Women):
- LNS14000002 = Women unemployment rate
- LNS12000002 = Women employed

## CRITICAL RULES FOR EXPLANATIONS

**DO NOT HALLUCINATE DATES!** Only use dates that come directly from the data. If you don't know the exact date, say "recent data" or "latest available".

**PAYROLLS = FOCUS ON CHANGES, NOT LEVELS!** For employment/payroll data:
- BAD: "Total employment is 159.5 million"
- GOOD: "The economy added 150,000 jobs last month" or "Job growth has averaged 200K/month"
- Always emphasize monthly gains, 3-month averages, or year-over-year changes
- The LEVEL of employment matters far less than the CHANGE

## RESPONSE FORMAT

Return JSON:
```json
{{
    "missing_dimensions": ["dimension 1", "dimension 2"],
    "additional_series": ["SERIES1", "SERIES2"],
    "reasoning": "Why these series complete the picture",
    "augmented_explanation": "Updated explanation covering all dimensions"
}}
```

If the plan is already comprehensive, return empty additional_series.
Only suggest series you're confident exist in FRED."""

    # Generate suggestions in parallel (with timeout to prevent hanging)
    LLM_TIMEOUT = 45  # seconds
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claude_future = executor.submit(call_claude, augment_prompt)
        gemini_future = executor.submit(call_gemini, augment_prompt)

        try:
            claude_result = claude_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            claude_result = None
            if verbose:
                print(f"    Claude augment timed out or failed: {e}")

        try:
            gemini_result = gemini_future.result(timeout=LLM_TIMEOUT)
        except (concurrent.futures.TimeoutError, Exception) as e:
            gemini_result = None
            if verbose:
                print(f"    Gemini augment timed out or failed: {e}")

    if verbose:
        print(f"    Claude suggests: {claude_result.get('additional_series', []) if claude_result else 'FAILED'}")
        print(f"    Gemini suggests: {gemini_result.get('additional_series', []) if gemini_result else 'FAILED'}")

    # Handle failures
    if not claude_result and not gemini_result:
        return {
            'additional_series': [],
            'combined_series': existing_series,
            'augmented_explanation': existing_explanation,
            'augmentation_metadata': {'error': 'Both models failed'}
        }

    if not claude_result:
        return _finalize_augmentation(existing_series, existing_explanation, gemini_result, 'gemini')

    if not gemini_result:
        return _finalize_augmentation(existing_series, existing_explanation, claude_result, 'claude')

    # Both succeeded - have GPT judge
    if verbose:
        print(f"  GPT judging augmentation suggestions...")

    judgment = _judge_augmentations(query, existing_series, claude_result, gemini_result)

    if not judgment:
        # Fallback to Claude's suggestions
        return _finalize_augmentation(existing_series, existing_explanation, claude_result, 'claude')

    if verbose:
        print(f"    Final additions: {judgment.get('additional_series', [])}")

    return _finalize_augmentation(
        existing_series,
        existing_explanation,
        judgment,
        f"merged ({judgment.get('winner', 'gpt')})"
    )


def _judge_augmentations(
    query: str,
    existing_series: list,
    suggestion_a: Dict,
    suggestion_b: Dict
) -> Optional[Dict]:
    """Have GPT judge two augmentation suggestions and merge the best."""
    judge_prompt = f"""You are an expert economist evaluating two suggestions for augmenting a FRED data query plan.

USER QUERY: "{query}"
EXISTING SERIES: {existing_series}

SUGGESTION A (what to add):
- Missing dimensions: {suggestion_a.get('missing_dimensions', [])}
- Additional series: {suggestion_a.get('additional_series', [])}
- Reasoning: {suggestion_a.get('reasoning', '')}

SUGGESTION B (what to add):
- Missing dimensions: {suggestion_b.get('missing_dimensions', [])}
- Additional series: {suggestion_b.get('additional_series', [])}
- Reasoning: {suggestion_b.get('reasoning', '')}

## EVALUATION CRITERIA:
1. **Relevance**: Do the suggested series actually address the query?
2. **Validity**: Are these real FRED series IDs? (Reject made-up IDs)
3. **Completeness**: Do the additions cover important missing dimensions?
4. **Non-redundancy**: Avoid adding series that measure the same thing as existing ones

## RESPONSE

Return JSON:
```json
{{
    "winner": "A" or "B" or "tie",
    "additional_series": ["SERIES1", "SERIES2"],
    "missing_dimensions": ["dimension 1", "dimension 2"],
    "reasoning": "Why these additions improve the answer",
    "augmented_explanation": "Updated explanation covering original + new series"
}}
```

Combine the best suggestions from both. Remove any series you're unsure about."""

    response = call_gpt(judge_prompt)
    if not response:
        return None

    return _extract_json(response)


def _finalize_augmentation(
    existing_series: list,
    existing_explanation: str,
    augmentation: Dict,
    source: str
) -> Dict:
    """Finalize the augmentation result."""
    additional = augmentation.get('additional_series', [])

    # Remove duplicates and ensure we don't add series that already exist
    additional = [s for s in additional if s not in existing_series]

    # Combine series (existing first, then additions)
    combined = existing_series + additional

    return {
        'additional_series': additional,
        'combined_series': combined,
        'augmented_explanation': augmentation.get('augmented_explanation', existing_explanation),
        'missing_dimensions': augmentation.get('missing_dimensions', []),
        'augmentation_metadata': {
            'source': source,
            'reasoning': augmentation.get('reasoning', ''),
            'original_series': existing_series,
            'added_series': additional
        }
    }


# ============================================================================
# PRESENTATION VALIDATION: Determine how to display each series (stock/flow/rate)
# ============================================================================

def validate_presentation(
    query: str,
    series_data: list,
    verbose: bool = False
) -> Dict:
    """
    Determine the appropriate presentation format for each series based on
    economic concepts: stock vs flow vs rate.

    This uses AI to apply economic reasoning rather than hardcoding series IDs.

    Args:
        query: The user's original question
        series_data: List of dicts with 'id', 'title', 'units', and optionally 'latest_value'

    Returns:
        Dict mapping series_id to presentation config:
        {
            "SERIES_ID": {
                "display_as": "level" | "change" | "mom_change" | "yoy_change",
                "category": "stock" | "flow" | "rate",
                "reasoning": "why this presentation"
            }
        }
    """
    if not series_data:
        return {}

    if verbose:
        print(f"  Validating presentation for {len(series_data)} series...")

    # Format series info for the prompt
    series_desc = "\n".join([
        f"- {s.get('id', 'Unknown')}: {s.get('title', 'No title')} (units: {s.get('units', 'unknown')})"
        for s in series_data
    ])

    presentation_prompt = f"""You are an expert economist determining how to present economic data.

USER QUERY: "{query}"

SERIES TO DISPLAY:
{series_desc}

## KEY ECONOMIC CONCEPT: Stock vs Flow vs Rate

**STOCK** = Cumulative total at a point in time
- Examples: Total employment (159M jobs), GDP level, debt level, price index level, wealth
- Problem: "159.5 million jobs" doesn't tell you if things are good or bad
- Solution: Show as CHANGE (month-over-month or year-over-year)

**FLOW** = Activity measured over a period (already "per period")
- Examples: Initial jobless claims (200K this week), monthly job gains, quarterly GDP growth, income per month
- Why level is OK: "200K filed claims this week" IS the meaningful number
- Solution: Show as LEVEL (it's already a flow measure)

**RATE** = Already a percentage or ratio
- Examples: Unemployment rate (4.4%), interest rates, inflation rate (YoY %), labor force participation
- Why level is OK: It's already normalized/comparable
- Solution: Show as LEVEL

## YOUR TASK

For each series, determine:
1. Is it a STOCK, FLOW, or RATE?
2. What's the best display format?

## DISPLAY FORMAT OPTIONS:
- "level": Show the raw value (good for flows and rates)
- "mom_change": Show month-over-month change (good for stocks like total payrolls)
- "yoy_change": Show year-over-year change (good for price indexes, GDP level)
- "yoy_pct": Show as year-over-year percent change (already computed for some series)

## COMMON SERIES GUIDANCE:

STOCKS (show as change):
- PAYEMS, MANEMP, USLAH, etc. (total employment) → mom_change (NEVER yoy_change!)
  * Economists report jobs as "+256K this month" not "0.37% YoY growth"
  * YoY % for employment is WRONG - always use monthly job gains
- CPIAUCSL (CPI index level) → yoy_change or yoy_pct
- GDP level → yoy_change

FLOWS (level is fine):
- ICSA (initial claims per week) → level
- Job gains/losses per month → level
- JTSJOL (job openings) → level (it's a count at a point, but changes rapidly so level is meaningful)

RATES (level is fine):
- UNRATE (unemployment rate) → level
- FEDFUNDS (interest rate) → level
- Any series already in "Percent" or "% Change" → level

## RESPONSE FORMAT
Return JSON only:
```json
{{
    "presentations": {{
        "SERIES_ID_1": {{
            "display_as": "mom_change",
            "category": "stock",
            "reasoning": "Total payrolls is a stock - showing monthly change is more meaningful than 159M level"
        }},
        "SERIES_ID_2": {{
            "display_as": "level",
            "category": "rate",
            "reasoning": "Unemployment rate is already a percentage - level is appropriate"
        }}
    }}
}}
```"""

    # Use GPT for this judgment task
    response = call_gpt(presentation_prompt)

    # Known series that should NEVER be shown as raw levels
    # Stock series need to show changes (cumulative totals where level is less meaningful)
    KNOWN_STOCKS = {
        # Employment stocks (total workers - show MONTHLY job change, NOT YoY %)
        # Economists report payrolls as "+256K jobs" not "0.37% YoY growth"
        'PAYEMS': 'mom_change',     # Total nonfarm payrolls → show as monthly job gains
        'MANEMP': 'mom_change',     # Manufacturing employment
        'USCONS': 'mom_change',     # Construction employment
        'USHCS': 'mom_change',      # Healthcare employment
        'USLAH': 'mom_change',      # Leisure & hospitality employment
        'USINFO': 'mom_change',     # Information employment
        'USTRADE': 'mom_change',    # Trade employment
        'USGOVT': 'mom_change',     # Government employment
        'USPBS': 'mom_change',      # Professional services employment
        'USMINE': 'mom_change',     # Mining employment
        'USGOOD': 'mom_change',     # Goods-producing employment
        'CES0500000001': 'mom_change',  # Total private employment
        'LNS12000000': 'mom_change',    # Employment level (household survey)
        'CE16OV': 'mom_change',         # Civilian employment level

        # GDP and production (show growth rates)
        'GDPC1': 'yoy_change',      # Real GDP
        'GDP': 'yoy_change',        # Nominal GDP
        'INDPRO': 'yoy_change',     # Industrial production
        'IPMAN': 'yoy_change',      # Manufacturing production

        # Consumer spending (show growth rates)
        'PCE': 'yoy_change',        # Personal consumption expenditures
        'PCEC96': 'yoy_change',     # Real PCE
        'RSAFS': 'yoy_change',      # Retail sales
        'RSXFS': 'yoy_change',      # Retail sales ex food services

        # Price indices (show inflation rates)
        'CPIAUCSL': 'yoy_change',   # CPI all items
        'CPILFESL': 'yoy_change',   # Core CPI
        'PCEPI': 'yoy_change',      # PCE price index
        'PCEPILFE': 'yoy_change',   # Core PCE
        'CSUSHPINSA': 'yoy_change', # Case-Shiller home price index
        'MSPUS': 'yoy_change',      # Median home sale price
        'CUSR0000SEHA': 'yoy_change',  # Shelter CPI
        'CUSR0000SAF11': 'yoy_change', # Food CPI
        'CUUR0000SETB01': 'yoy_change', # Gas CPI

        # Money supply and Fed balance sheet (show growth)
        'M2SL': 'yoy_change',       # M2 money supply
        'M1SL': 'yoy_change',       # M1 money supply
        'WALCL': 'yoy_change',      # Fed total assets
        'GFDEBTN': 'yoy_change',    # Federal debt total

        # Wages (show growth)
        'CES0500000003': 'yoy_change',   # Avg hourly earnings
        'LES1252881600Q': 'yoy_change',  # Real median wages
        'AHETPI': 'yoy_change',          # Production worker hourly earnings

        # Trade (show growth)
        'EXPGS': 'yoy_change',      # Exports
        'IMPGS': 'yoy_change',      # Imports
        'BOPGSTB': 'yoy_change',    # Trade balance
    }

    # Rate/flow series that should show as levels (already per-period or percentages)
    KNOWN_RATES = {
        # Unemployment rates
        'UNRATE', 'U6RATE', 'LNS14000006', 'LNS14000009', 'LNS14000003',
        'LNS14000001', 'LNS14000002',
        # Interest rates
        'FEDFUNDS', 'DGS10', 'DGS2', 'DGS30', 'MORTGAGE30US', 'PRIME',
        # Participation rates
        'CIVPART', 'LNS11300006', 'LNS11300009',
        # Sentiment indices (already normalized)
        'UMCSENT',
        # Housing flows (monthly rates, not cumulative)
        'HOUST', 'HSN1F', 'PERMIT', 'EXHOSLUSM495S',
        # Claims (weekly flow, not cumulative)
        'ICSA', 'CCSA',
    }

    def get_smart_default(series_id):
        """Use known series characteristics for smart defaults."""
        if series_id in KNOWN_STOCKS:
            return {'display_as': KNOWN_STOCKS[series_id], 'category': 'stock', 'reasoning': 'known stock series'}
        if series_id in KNOWN_RATES:
            return {'display_as': 'level', 'category': 'rate', 'reasoning': 'known rate/flow series'}
        # Pattern-based detection for rates/percentages
        if 'RATE' in series_id or series_id.startswith('LNS14') or series_id.startswith('U6'):
            return {'display_as': 'level', 'category': 'rate', 'reasoning': 'rate series (pattern match)'}
        # Employment-population ratios show as levels
        if series_id.startswith('LNS12') or series_id.startswith('LNS11'):
            return {'display_as': 'level', 'category': 'rate', 'reasoning': 'employment ratio series'}
        # Default to level for unknown series (safer than wrong transformation)
        return {'display_as': 'level', 'category': 'unknown', 'reasoning': 'unknown series - defaulting to level'}

    if not response:
        if verbose:
            print("    Presentation validation failed, using smart defaults")
        return {s.get('id'): get_smart_default(s.get('id')) for s in series_data}

    result = _extract_json(response)

    if not result or 'presentations' not in result:
        if verbose:
            print("    Presentation parse failed, using smart defaults")
        return {s.get('id'): get_smart_default(s.get('id')) for s in series_data}

    if verbose:
        for sid, config in result.get('presentations', {}).items():
            print(f"    {sid}: {config.get('display_as')} ({config.get('category')})")

    return result.get('presentations', {})


# Quick test function
def test_ensemble():
    """Test the ensemble system with a sample query."""
    test_prompt = """You are an expert economist specializing in FRED data.
Return a JSON query plan with: series (list of FRED IDs), show_yoy (bool), combine_chart (bool), explanation (string)."""

    print("Testing ensemble query plan generation...")
    plan, judgment = generate_ensemble_plan("inflation", test_prompt)

    print(f"\nFinal Plan: {json.dumps(plan, indent=2)}")
    print(f"\nJudgment: {json.dumps(judgment, indent=2)}")


def test_app_integration():
    """Test the app integration function."""
    # Simplified economist prompt for testing
    economist_prompt = """You are an expert economist helping interpret economic data questions for FRED.

Return JSON with:
- series: list of FRED series IDs
- explanation: why these series answer the question
- show_yoy: whether to show year-over-year changes
- combine_chart: whether to combine series on one chart
- search_terms: terms to search if you don't know exact IDs

WELL-KNOWN SERIES:
- CPIAUCSL = CPI All Items
- UNRATE = Unemployment rate
- PAYEMS = Nonfarm payrolls
- FEDFUNDS = Federal funds rate
- GDPC1 = Real GDP

USER QUERY: """

    print("Testing app integration...")
    result = call_ensemble_for_app(
        "What's happening with semiconductor employment?",
        economist_prompt,
        verbose=True
    )

    print(f"\nResult: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'app':
        test_app_integration()
    else:
        test_ensemble()
