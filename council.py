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
from typing import Optional

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
    "id": "gpt-4o",
    "model": "openai/gpt-4o",
    "label": "GPT-4o (Chairman)",
}

REQUEST_TIMEOUT = 120  # seconds per call
MAX_RETRIES = 2
MIN_QUORUM = 2  # minimum councilors needed to proceed

# ── Core API call ──────────────────────────────────────────────────────────────

async def call_model(
    client: httpx.AsyncClient, model: str, messages: list, label: str = ""
) -> tuple[bool, str]:
    """Call a model via OpenRouter. Returns (success, content) tuple."""
    last_error = None
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
                retry_after = float(resp.headers.get("Retry-After", 2 * (attempt + 1)))
                last_error = f"HTTP {resp.status_code}"
                if attempt < MAX_RETRIES:
                    print(f"   ⏳ {label or model}: {last_error}, retrying in {retry_after}s...", file=sys.stderr)
                    await asyncio.sleep(retry_after)
                    continue
                return (False, f"{label or model}: {last_error} after {MAX_RETRIES + 1} attempts")

            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            return (True, content)

        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                wait = 2 * (attempt + 1)
                print(f"   ⏳ {label or model}: {last_error}, retrying in {wait}s...", file=sys.stderr)
                await asyncio.sleep(wait)
                continue
            return (False, f"{label or model}: {last_error}")

    return (False, f"{label or model}: {last_error}")


# ── Stage 1: First Opinions ────────────────────────────────────────────────────

async def stage1_first_opinions(client: httpx.AsyncClient, question: str) -> tuple[list[dict], list[dict]]:
    """Ask all councilors the question in parallel. Returns (successes, errors)."""
    print("⚖️  Stage 1: Gathering first opinions...", file=sys.stderr)

    system_prompt = (
        "You are a council member providing an expert, independent opinion. "
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
    labels = ["Model A", "Model B", "Model C"]
    others = [a for a in answers if a["id"] != exclude_id]
    # Shuffle so models can't pattern-match on ordering
    random.shuffle(others)
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
        "You are evaluating answers from other AI models to the same question. "
        "The models are anonymized as Model A, B, C. Do not play favorites. "
        "Focus on accuracy, completeness, and insight."
    )

    async def review_one(councilor: dict) -> tuple[dict, bool, str]:
        anon_answers = anonymize_answers(answers, councilor["id"])
        prompt = (
            f"Original question: {question}\n\n"
            f"Here are three other answers:\n\n{anon_answers}\n\n"
            "Please:\n"
            "1. Rank these answers from best to worst (Model A, B, or C) with brief reasoning\n"
            "2. Note any significant disagreements or contradictions between them\n"
            "3. Identify what each answer got right or missed\n"
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

    # Strategy 3: Find outermost { ... } block
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
    """Chairman synthesizes everything into a final answer + disagreement breakdown."""
    print("👑  Stage 3: Chairman synthesizing...", file=sys.stderr)

    # Build the full picture for the chairman
    answers_block = "\n\n".join(
        f"**{a['label']}:**\n{a['answer']}" for a in answers
    )

    if fast_mode or not reviews:
        chairman_prompt = (
            f"You are the Chairman of an LLM Council. Your council was asked:\n\n"
            f"**QUESTION:** {question}\n\n"
            f"---\n\n"
            f"**INDIVIDUAL ANSWERS:**\n\n{answers_block}\n\n"
            f"---\n\n"
        )
    else:
        reviews_block = "\n\n".join(
            f"**{r['label']}'s review of others:**\n{r['review']}" for r in reviews
        )
        chairman_prompt = (
            f"You are the Chairman of an LLM Council. Your council was asked:\n\n"
            f"**QUESTION:** {question}\n\n"
            f"---\n\n"
            f"**INDIVIDUAL ANSWERS:**\n\n{answers_block}\n\n"
            f"---\n\n"
            f"**PEER REVIEWS:**\n\n{reviews_block}\n\n"
            f"---\n\n"
        )

    chairman_prompt += (
        "Your job: Produce a response in the following JSON format (and ONLY JSON, no markdown wrapper):\n\n"
        '{\n'
        '  "final_answer": "Your comprehensive synthesized answer here. Draw on the best insights from all models. Be definitive. 300-600 words.",\n'
        '  "disagreements": [\n'
        '    {\n'
        '      "topic": "Short label for what they disagreed on",\n'
        '      "summary": "What the disagreement was and why it matters",\n'
        '      "chairman_verdict": "Your take on which view is more accurate and why"\n'
        '    }\n'
        '  ],\n'
        '  "consensus_points": ["Point 1 all models agreed on", "Point 2..."],\n'
        '  "confidence": "high|medium|low",\n'
        '  "confidence_note": "Brief note on why (e.g. models strongly aligned, or significant uncertainty exists)"\n'
        '}'
    )

    ok, raw = await call_model(
        client,
        CHAIRMAN["model"],
        [
            {"role": "system", "content": "You are a synthesis expert. Output only valid JSON, no markdown code blocks."},
            {"role": "user", "content": chairman_prompt},
        ],
        label=CHAIRMAN["label"],
    )

    if not ok:
        print(f"   ✗ Chairman call failed: {raw}", file=sys.stderr)
        return {
            "final_answer": f"Chairman failed to respond: {raw}",
            "disagreements": [],
            "consensus_points": [],
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
            "final_answer": raw,
            "disagreements": [],
            "consensus_points": [],
            "confidence": "unknown",
            "confidence_note": "Chairman response could not be parsed as JSON.",
        }

    # Validate required keys exist and have correct types
    if not isinstance(synthesis.get("final_answer"), str):
        synthesis["final_answer"] = str(synthesis.get("final_answer", ""))
    if not isinstance(synthesis.get("disagreements"), list):
        synthesis["disagreements"] = []
    if not isinstance(synthesis.get("consensus_points"), list):
        synthesis["consensus_points"] = []
    if not isinstance(synthesis.get("confidence"), str):
        synthesis["confidence"] = "unknown"
    if not isinstance(synthesis.get("confidence_note"), str):
        synthesis["confidence_note"] = ""

    print("   ✓ Chairman done", file=sys.stderr)
    return synthesis


# ── Main ───────────────────────────────────────────────────────────────────────

async def run_council(question: str, fast: bool = False) -> dict:
    if not OPENROUTER_API_KEY:
        print(json.dumps({"error": "OPENROUTER_API_KEY not set in environment"}))
        sys.exit(1)

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

    # Assemble full output
    output = {
        "question": question,
        "final_answer": synthesis.get("final_answer", ""),
        "disagreements": synthesis.get("disagreements", []),
        "consensus_points": synthesis.get("consensus_points", []),
        "confidence": synthesis.get("confidence", "unknown"),
        "confidence_note": synthesis.get("confidence_note", ""),
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
        print(json.dumps({"error": str(e)}, indent=2, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
