#!/usr/bin/env python3
"""
LLM Council - Multi-model deliberation via OpenRouter
Usage: python3 council.py "Your question here"
       python3 council.py --fast "Your question here"   (skip cross-review)
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

COUNCILORS = [
    {"id": "deepseek-r1",   "model": "deepseek/deepseek-r1-0528:free",                   "label": "DeepSeek R1",       "role": "Reasoner"},
    {"id": "hermes-405b",   "model": "nousresearch/hermes-3-llama-3.1-405b:free",         "label": "Hermes 3 405B",     "role": "Knowledge"},
    {"id": "qwen3-coder",   "model": "qwen/qwen3-coder:free",                             "label": "Qwen3 Coder 480B",  "role": "Structuralist"},
    {"id": "llama-33-70b",  "model": "meta-llama/llama-3.3-70b-instruct:free",            "label": "Llama 3.3 70B",     "role": "Generalist"},
]

CHAIRMAN = {
    "id": "kimi-k2.5",
    "model": "moonshotai/kimi-k2.5:free",
    "label": "Kimi K2.5 (Chairman)",
}

REQUEST_TIMEOUT = 120  # seconds per call
MAX_RETRIES = 2
MIN_QUORUM = 2  # minimum councilors needed to proceed

# ── Core API call ──────────────────────────────────────────────────────────────

async def call_model(
    client: httpx.AsyncClient, model: str, messages: list, label: str = ""
) -> tuple[bool, str]:
    """Call a model via OpenRouter. Returns (success, content) tuple."""
    tag = label or model

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://openclaw.ai",
                    "X-Title": "LLM Council Skill",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 1500,
                    "temperature": 0.7,
                },
                timeout=REQUEST_TIMEOUT,
            )

            # Retry on rate limit or server error
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("Retry-After", 2 * (attempt + 1)))
                error = f"HTTP {resp.status_code}"
                if attempt < MAX_RETRIES:
                    print(f"   ⏳ {tag}: {error}, retrying in {wait}s...", file=sys.stderr)
                    await asyncio.sleep(wait)
                    continue
                return (False, f"{tag}: {error} after {MAX_RETRIES + 1} attempts")

            resp.raise_for_status()
            data = resp.json()

            # Validate response structure
            choices = data.get("choices")
            if not choices or not isinstance(choices, list):
                error = "Invalid API response: missing or empty choices"
            else:
                content = choices[0].get("message", {}).get("content")
                if content is None:
                    error = "Invalid API response: missing message content"
                else:
                    return (True, content.strip())

        except Exception as e:
            error = str(e)

        # Shared retry-or-fail for all error paths
        if attempt < MAX_RETRIES:
            wait = 2 * (attempt + 1)
            print(f"   ⏳ {tag}: {error}, retrying in {wait}s...", file=sys.stderr)
            await asyncio.sleep(wait)
        else:
            return (False, f"{tag}: {error}")

    return (False, f"{tag}: unknown error")


# ── Stage 1: First Opinions ────────────────────────────────────────────────────

async def stage1_first_opinions(client: httpx.AsyncClient, question: str) -> tuple[list[dict], list[dict]]:
    """Ask all councilors the question in parallel. Returns (successes, errors)."""
    print("⚖️  Stage 1: Gathering first opinions...", file=sys.stderr)

    system_prompt = (
        "You are a strategic planning advisor on a council that refines visions into actionable strategic plans. "
        "Focus on: deliverables, milestones, success criteria, risks, resource needs, timeline phases, "
        "go/no-go decision points, and moats (defensible strategic advantages). "
        "Do NOT recommend specific technologies, tools, vendors, or implementation details "
        "— a separate product manager handles those decisions. "
        "Stay at the strategic level: what needs to be built, why, in what order, "
        "how to measure success, what could go wrong, and what makes this defensible. "
        "Be direct, thorough, and honest. Do not hedge unnecessarily. "
        "Aim for 200-400 words."
    )

    tasks = [
        call_model(
            client,
            c["model"],
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            label=c["label"],
        )
        for c in COUNCILORS
    ]

    results = await asyncio.gather(*tasks)

    successes = []
    errors = []
    for councilor, (ok, content) in zip(COUNCILORS, results):
        if ok:
            successes.append({**councilor, "answer": content})
            print(f"   ✓ {councilor['label']}", file=sys.stderr)
        else:
            errors.append({"model": councilor["label"], "error": content})
            print(f"   ✗ {councilor['label']}: {content}", file=sys.stderr)

    if len(successes) < MIN_QUORUM:
        raise RuntimeError(
            f"Only {len(successes)} councilor(s) succeeded — minimum {MIN_QUORUM} required. "
            f"Errors: {errors}"
        )

    return successes, errors


# ── Stage 2: Anonymous Cross-Review ───────────────────────────────────────────

def anonymize_answers(answers: list[dict], exclude_id: str) -> str:
    """Build an anonymized view of other councilors' answers for review."""
    others = [a for a in answers if a["id"] != exclude_id]
    # Shuffle so models can't pattern-match on ordering
    random.shuffle(others)
    labels = [f"Model {chr(65 + i)}" for i in range(len(others))]
    sections = []
    for label, other in zip(labels, others):
        sections.append(f"**{label}:**\n{other['answer']}")
    return "\n\n---\n\n".join(sections)


async def stage2_reviews(
    client: httpx.AsyncClient, question: str, answers: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Each councilor reviews the others anonymously. Returns (successes, errors)."""
    print("🔍  Stage 2: Cross-reviewing...", file=sys.stderr)

    review_system = (
        "You are evaluating strategic plans from other AI models for the same initiative. "
        "The models are anonymized as Model A, B, C. Do not play favorites. "
        "Evaluate strategic thinking quality: Are deliverables clear and measurable? "
        "Are risks identified with viable mitigations? Are phases sequenced logically? "
        "Are success criteria specific enough to be actionable? "
        "Are moats clearly identified and defensible? "
        "Ignore any specific technology or tool recommendations — those are out of scope."
    )

    async def review_one(councilor: dict) -> tuple[dict, bool, str]:
        anon_answers = anonymize_answers(answers, councilor["id"])
        prompt = (
            f"Strategic initiative: {question}\n\n"
            f"Here are three strategic plans from other advisors:\n\n{anon_answers}\n\n"
            "Please:\n"
            "1. Rank these plans from strongest to weakest (Model A, B, or C) "
            "based on strategic clarity, risk coverage, and actionability\n"
            "2. Note any significant strategic disagreements — different priorities, "
            "conflicting phase sequences, or incompatible success criteria\n"
            "3. Identify strategic gaps: missing risks, vague deliverables, "
            "unrealistic timelines, weak or absent moats, or absent decision gates\n"
            "Ignore any specific technology or tool recommendations. "
            "Be specific and critical. 150-300 words."
        )
        ok, content = await call_model(
            client,
            councilor["model"],
            [
                {"role": "system", "content": review_system},
                {"role": "user", "content": prompt},
            ],
            label=councilor["label"],
        )
        return councilor, ok, content

    tasks = [review_one(c) for c in answers]
    results = await asyncio.gather(*tasks)

    successes = []
    errors = []
    for councilor, ok, content in results:
        if ok:
            successes.append({**councilor, "review": content})
            print(f"   ✓ {councilor['label']} reviewed", file=sys.stderr)
        else:
            errors.append({"model": councilor["label"], "error": content})
            print(f"   ✗ {councilor['label']} review failed: {content}", file=sys.stderr)

    return successes, errors


# ── Stage 3: Chairman Synthesis ────────────────────────────────────────────────

def parse_chairman_json(raw: str) -> dict:
    """Parse Chairman response as JSON with multiple fallback strategies."""

    # Strategy 1: Direct parse (clean JSON)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract JSON from markdown fences
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find outermost { ... } block (greedy — handles nested braces)
    brace_match = re.search(r"\{[\s\S]*\}", raw)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # All strategies failed
    return None


async def stage3_chairman(
    client: httpx.AsyncClient,
    question: str,
    answers: list[dict],
    reviews: list[dict] | None,
    fast_mode: bool = False,
) -> dict:
    """Chairman synthesizes strategic plans into a unified strategic plan."""
    print("👑  Stage 3: Chairman synthesizing...", file=sys.stderr)

    # Build the full picture for the chairman
    answers_block = "\n\n".join(
        f"**{a['label']}:**\n{a['answer']}" for a in answers
    )

    chairman_prompt = (
        f"You are the Chairman of a Strategic Planning Council. "
        f"Your council was asked to create a strategic plan for:\n\n"
        f"**INITIATIVE:** {question}\n\n"
        f"---\n\n"
        f"**INDIVIDUAL STRATEGIC PLANS:**\n\n{answers_block}\n\n"
        f"---\n\n"
    )

    if not fast_mode and reviews:
        reviews_block = "\n\n".join(
            f"**{r['label']}'s review of others:**\n{r['review']}" for r in reviews
        )
        chairman_prompt += f"**PEER REVIEWS:**\n\n{reviews_block}\n\n---\n\n"

    chairman_prompt += (
        "Your job: Synthesize all perspectives into a unified strategic plan. "
        "Do NOT recommend specific technologies, tools, or vendors. "
        "Produce a response in the following JSON format (and ONLY JSON, no markdown wrapper):\n\n"
        '{\n'
        '  "executive_summary": "A 300-600 word strategic synthesis. What is the initiative, '
        'why it matters, and the recommended strategic approach. Draw on the best insights '
        'from all advisors. Be definitive.",\n'
        '  "deliverables": [\n'
        '    {\n'
        '      "name": "Short name for the deliverable",\n'
        '      "description": "What this deliverable is and why it matters",\n'
        '      "phase": "Which phase this belongs to (e.g. Phase 1, Phase 2)"\n'
        '    }\n'
        '  ],\n'
        '  "success_criteria": [\n'
        '    {\n'
        '      "metric": "What to measure",\n'
        '      "target": "Specific target or threshold",\n'
        '      "rationale": "Why this metric matters"\n'
        '    }\n'
        '  ],\n'
        '  "phases": [\n'
        '    {\n'
        '      "name": "Phase name (e.g. Phase 1: Foundation)",\n'
        '      "duration": "Estimated duration (e.g. 2-4 weeks)",\n'
        '      "objectives": ["Key objective 1", "Key objective 2"],\n'
        '      "decision_point": "What must be true to proceed to the next phase"\n'
        '    }\n'
        '  ],\n'
        '  "risks": [\n'
        '    {\n'
        '      "risk": "Description of the risk",\n'
        '      "severity": "high|medium|low",\n'
        '      "mitigation": "How to mitigate this risk"\n'
        '    }\n'
        '  ],\n'
        '  "moats": [\n'
        '    {\n'
        '      "type": "Category of strategic advantage (e.g. Network Effect, Data Advantage, Switching Cost, Brand, Expertise)",\n'
        '      "description": "What this moat is and how it works",\n'
        '      "durability": "How long-lasting and defensible this advantage is"\n'
        '    }\n'
        '  ],\n'
        '  "strategic_priorities": ["Priority 1 all advisors agreed on", "Priority 2..."],\n'
        '  "resource_considerations": "High-level resource needs: team size, skill areas, '
        'budget range, timeline constraints. No specific tool or vendor names.",\n'
        '  "go_no_go_criteria": ["Criterion that must be met to proceed", "Another criterion..."],\n'
        '  "disagreements": [\n'
        '    {\n'
        '      "topic": "Short label for what advisors disagreed on",\n'
        '      "summary": "What the strategic disagreement was and why it matters",\n'
        '      "chairman_verdict": "Your take on which strategic approach is stronger and why"\n'
        '    }\n'
        '  ],\n'
        '  "confidence": "high|medium|low",\n'
        '  "confidence_note": "Brief note on confidence level"\n'
        '}'
    )

    ok, raw = await call_model(
        client,
        CHAIRMAN["model"],
        [
            {"role": "system", "content": "You are a strategic planning synthesis expert. Your job is to distill multiple strategic perspectives into one cohesive strategic plan. Output only valid JSON, no markdown code blocks."},
            {"role": "user", "content": chairman_prompt},
        ],
        label=CHAIRMAN["label"],
    )

    if not ok:
        print(f"   ✗ Chairman call failed: {raw}", file=sys.stderr)
        return {
            "executive_summary": f"Chairman failed to respond: {raw}",
            "deliverables": [],
            "success_criteria": [],
            "phases": [],
            "risks": [],
            "moats": [],
            "strategic_priorities": [],
            "resource_considerations": "",
            "go_no_go_criteria": [],
            "disagreements": [],
            "confidence": "unknown",
            "confidence_note": "Chairman call failed.",
        }

    # Log raw response for debugging
    print(f"   📝 Chairman raw response length: {len(raw)} chars", file=sys.stderr)

    # Parse JSON with multiple fallback strategies
    synthesis = parse_chairman_json(raw)
    if synthesis is None:
        print(f"   ⚠️  Chairman JSON parse failed, using raw text fallback", file=sys.stderr)
        print(f"   📝 Raw response (first 200 chars): {raw[:200]}", file=sys.stderr)
        synthesis = {
            "executive_summary": raw,
            "deliverables": [],
            "success_criteria": [],
            "phases": [],
            "risks": [],
            "moats": [],
            "strategic_priorities": [],
            "resource_considerations": "",
            "go_no_go_criteria": [],
            "disagreements": [],
            "confidence": "unknown",
            "confidence_note": "Chairman response could not be parsed as JSON.",
        }

    # Validate required keys exist and have correct types
    _SCHEMA = {
        "executive_summary":       (str, ""),
        "deliverables":            (list, []),
        "success_criteria":        (list, []),
        "phases":                  (list, []),
        "risks":                   (list, []),
        "moats":                   (list, []),
        "strategic_priorities":    (list, []),
        "resource_considerations": (str, ""),
        "go_no_go_criteria":       (list, []),
        "disagreements":           (list, []),
        "confidence":              (str, "unknown"),
        "confidence_note":         (str, ""),
    }
    for key, (expected_type, default) in _SCHEMA.items():
        val = synthesis.get(key)
        if not isinstance(val, expected_type):
            synthesis[key] = str(val) if expected_type is str and val is not None else default

    print("   ✓ Chairman done", file=sys.stderr)
    return synthesis


# ── Main ───────────────────────────────────────────────────────────────────────

async def run_council(question: str, fast: bool = False) -> dict:

    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    all_errors = []

    async with httpx.AsyncClient() as client:
        # Stage 1
        answers, stage1_errors = await stage1_first_opinions(client, question)
        all_errors.extend(stage1_errors)

        # Stage 2 (skip if --fast)
        reviews = None
        stage2_errors = []
        if not fast:
            reviews, stage2_errors = await stage2_reviews(client, question, answers)
            all_errors.extend(stage2_errors)
        else:
            print("⏩  Stage 2 skipped (--fast mode)", file=sys.stderr)

        # Stage 3
        synthesis = await stage3_chairman(client, question, answers, reviews, fast_mode=fast)

    duration = round(time.monotonic() - t0, 1)

    # Assemble full output (synthesis keys guaranteed by _SCHEMA validation)
    output = {
        "question": question,
        "executive_summary": synthesis["executive_summary"],
        "deliverables": synthesis["deliverables"],
        "success_criteria": synthesis["success_criteria"],
        "phases": synthesis["phases"],
        "risks": synthesis["risks"],
        "moats": synthesis["moats"],
        "strategic_priorities": synthesis["strategic_priorities"],
        "resource_considerations": synthesis["resource_considerations"],
        "go_no_go_criteria": synthesis["go_no_go_criteria"],
        "disagreements": synthesis["disagreements"],
        "confidence": synthesis["confidence"],
        "confidence_note": synthesis["confidence_note"],
        "individual_answers": [
            {"model": a["label"], "answer": a["answer"]} for a in answers
        ],
        "peer_reviews": [
            {"reviewer": r["label"], "review": r["review"]} for r in (reviews or [])
        ],
        "chairman": CHAIRMAN["label"],
        "council": [c["label"] for c in COUNCILORS],
        "stage2_skipped": fast,
        "run_started_at": started_at.isoformat(),
        "run_duration_seconds": duration,
        "errors": all_errors,
    }

    return output


def main():
    if not OPENROUTER_API_KEY:
        print("Error: OPENROUTER_API_KEY not set in environment", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="LLM Council - Multi-model deliberation via OpenRouter"
    )
    parser.add_argument("question", nargs="+", help="The question to deliberate on")
    parser.add_argument(
        "--fast", action="store_true",
        help="Skip Stage 2 (cross-review) for faster results (5 API calls instead of 9)"
    )
    args = parser.parse_args()

    question = " ".join(args.question)
    mode = " (fast mode)" if args.fast else ""
    print(f"🏛️  Convening the council{mode} for: {question[:80]}...\n", file=sys.stderr)

    try:
        result = asyncio.run(run_council(question, fast=args.fast))
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
