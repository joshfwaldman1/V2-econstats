#!/usr/bin/env python3
"""Base utilities for query plan generation agents."""

import json
import os
import time
import sys
from urllib.request import urlopen, Request

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def call_claude(prompt: str, retries: int = 3) -> dict:
    """Call Claude to generate a query plan with retries."""
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
            req = Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
            with urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                content = result['content'][0]['text']
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                return json.loads(content.strip())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  ERROR after {retries} attempts: {e}")
                return None
    return None


MULTI_CHART_GUIDANCE = """

## CRITICAL: COMPREHENSIVE RESPONSES
When there are multiple relevant series that tell different parts of the story, include ALL of them (up to 4 series). Do NOT be lazy and just pick one.

For example:
- "GDP" should include: annual growth (YoY), quarterly growth, core GDP (private demand), and GDPNow
- "Inflation" should include: headline CPI, core CPI, and possibly PCE
- "Jobs" should include: payrolls AND unemployment rate
- Each series should add unique insight - don't include redundant measures

The explanation field should briefly describe what EACH series measures and why it's included.
"""


def process_prompts(prompts: list, expert_prompt: str, output_file: str, category: str):
    """Process a list of prompts with the given expert prompt."""
    print(f"\n{'='*60}")
    print(f"AGENT: {category.upper()}")
    print(f"{'='*60}")
    print(f"Processing {len(prompts)} prompts...")

    plans = {}
    errors = []

    for i, prompt in enumerate(prompts):
        print(f"[{i+1}/{len(prompts)}] '{prompt}'")

        full_prompt = expert_prompt + MULTI_CHART_GUIDANCE + f"\n\nUSER QUERY: {prompt}"
        result = call_claude(full_prompt)

        if result and result.get('series'):
            plans[prompt] = {
                'series': result.get('series', []),
                'show_yoy': result.get('show_yoy', False),
                'combine_chart': result.get('combine_chart', False),
                'explanation': result.get('explanation', ''),
            }
            print(f"  -> {result.get('series', [])}")
        else:
            errors.append(prompt)
            print(f"  -> FAILED")

        time.sleep(0.3)  # Rate limiting

    # Save results
    with open(output_file, 'w') as f:
        json.dump(plans, f, indent=2)

    print(f"\n{category} COMPLETE: {len(plans)} plans, {len(errors)} errors")
    print(f"Saved to: {output_file}")
    return plans
