"""Tests for council.py — LLM Council pipeline."""

import json
import random
import pytest
import httpx
import respx

# Adjust path so we can import from parent
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import council


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_council_state():
    """Reset module-level state before each test to prevent pollution."""
    original_key = council.OPENROUTER_API_KEY
    original_retries = council.MAX_RETRIES
    original_random_state = random.getstate()
    yield
    council.OPENROUTER_API_KEY = original_key
    council.MAX_RETRIES = original_retries
    random.setstate(original_random_state)

MOCK_ANSWER = "This is a thoughtful model answer about the question."
MOCK_REVIEW = "Model A provided the best answer. Model B was too brief. Model C missed key points."

MOCK_CHAIRMAN_JSON = json.dumps({
    "final_answer": "The synthesized answer combining all perspectives.",
    "disagreements": [
        {
            "topic": "Approach to testing",
            "summary": "Models disagreed on whether unit or integration tests are more important.",
            "chairman_verdict": "Both are necessary; unit tests for speed, integration for confidence."
        }
    ],
    "consensus_points": ["All models agreed testing is essential.", "All recommended starting early."],
    "confidence": "high",
    "confidence_note": "Strong alignment across all councilors."
})


def mock_openrouter_success(content: str = MOCK_ANSWER):
    """Return a mock OpenRouter success response body."""
    return {
        "choices": [{"message": {"content": content}}]
    }


def mock_openrouter_error():
    """Return a 500 error response."""
    return httpx.Response(500, text="Internal Server Error")


# ── Stage 1 Tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stage1_parallel():
    """All 4 councilors called concurrently, response structure correct."""
    with respx.mock:
        respx.post(council.OPENROUTER_API_URL).respond(
            json=mock_openrouter_success()
        )
        async with httpx.AsyncClient() as client:
            successes, errors = await council.stage1_first_opinions(client, "What is Python?")

    assert len(successes) == 4
    assert len(errors) == 0
    for s in successes:
        assert "answer" in s
        assert "label" in s
        assert "id" in s
        assert s["answer"] == MOCK_ANSWER


@pytest.mark.asyncio
async def test_stage1_partial_failure():
    """One model fails, other 3 succeed, pipeline continues."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # Second model fails
            return httpx.Response(500, text="Server Error")
        return httpx.Response(200, json=mock_openrouter_success())

    council.MAX_RETRIES = 0

    with respx.mock:
        respx.post(council.OPENROUTER_API_URL).mock(side_effect=side_effect)
        async with httpx.AsyncClient() as client:
            successes, errors = await council.stage1_first_opinions(client, "Test question")

    assert len(successes) == 3
    assert len(errors) == 1
    assert "error" in errors[0]


@pytest.mark.asyncio
async def test_stage1_below_quorum():
    """3 models fail, only 1 succeeds — should raise RuntimeError."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:  # First 3 fail
            return httpx.Response(500, text="Server Error")
        return httpx.Response(200, json=mock_openrouter_success())

    council.MAX_RETRIES = 0

    with respx.mock:
        respx.post(council.OPENROUTER_API_URL).mock(side_effect=side_effect)
        async with httpx.AsyncClient() as client:
            with pytest.raises(RuntimeError, match="minimum"):
                await council.stage1_first_opinions(client, "Test question")


# ── Stage 2 Tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stage2_anonymization():
    """Reviewer doesn't see own answer, labels are Model A/B/C."""
    answers = [
        {"id": "model-1", "model": "test/model-1:free", "label": "Model 1", "answer": "Answer from model 1"},
        {"id": "model-2", "model": "test/model-2:free", "label": "Model 2", "answer": "Answer from model 2"},
        {"id": "model-3", "model": "test/model-3:free", "label": "Model 3", "answer": "Answer from model 3"},
        {"id": "model-4", "model": "test/model-4:free", "label": "Model 4", "answer": "Answer from model 4"},
    ]

    anon = council.anonymize_answers(answers, "model-2")

    # Model 2's answer should NOT appear
    assert "Answer from model 2" not in anon
    # Other answers should appear
    assert "Answer from model 1" in anon
    assert "Answer from model 3" in anon
    assert "Answer from model 4" in anon
    # Labels should be Model A, B, C
    assert "Model A" in anon
    assert "Model B" in anon
    assert "Model C" in anon
    # Real model names should NOT appear
    assert "Model 1" not in anon
    assert "Model 3" not in anon
    assert "Model 4" not in anon


@pytest.mark.asyncio
async def test_stage2_reviews():
    """Reviews are collected from all successful councilors."""
    answers = [
        {"id": "m1", "model": "test/m1:free", "label": "M1", "answer": "Answer 1"},
        {"id": "m2", "model": "test/m2:free", "label": "M2", "answer": "Answer 2"},
        {"id": "m3", "model": "test/m3:free", "label": "M3", "answer": "Answer 3"},
    ]

    with respx.mock:
        respx.post(council.OPENROUTER_API_URL).respond(
            json=mock_openrouter_success(MOCK_REVIEW)
        )
        async with httpx.AsyncClient() as client:
            successes, errors = await council.stage2_reviews(client, "Test?", answers)

    assert len(successes) == 3
    assert len(errors) == 0
    for s in successes:
        assert "review" in s
        assert s["review"] == MOCK_REVIEW


# ── Stage 3 Tests ─────────────────────────────────────────────────────────────

def test_stage3_json_parse_valid():
    """Chairman returns clean JSON — parsed correctly."""
    result = council.parse_chairman_json(MOCK_CHAIRMAN_JSON)
    assert result is not None
    assert result["confidence"] == "high"
    assert len(result["disagreements"]) == 1
    assert len(result["consensus_points"]) == 2


def test_stage3_json_parse_markdown_fenced():
    """Chairman wraps JSON in markdown fences — still parsed."""
    fenced = f"```json\n{MOCK_CHAIRMAN_JSON}\n```"
    result = council.parse_chairman_json(fenced)
    assert result is not None
    assert result["confidence"] == "high"


def test_stage3_json_parse_markdown_no_lang():
    """Chairman wraps JSON in fences without 'json' label."""
    fenced = f"```\n{MOCK_CHAIRMAN_JSON}\n```"
    result = council.parse_chairman_json(fenced)
    assert result is not None
    assert result["confidence"] == "high"


def test_stage3_json_parse_with_preamble():
    """Chairman adds text before JSON — still extracted."""
    with_preamble = f"Here is my synthesis:\n\n{MOCK_CHAIRMAN_JSON}"
    result = council.parse_chairman_json(with_preamble)
    assert result is not None
    assert "final_answer" in result


def test_stage3_json_parse_malformed():
    """Chairman returns garbage — returns None."""
    result = council.parse_chairman_json("This is not JSON at all, just a rambling answer.")
    assert result is None


def test_stage3_json_parse_partial():
    """Chairman returns incomplete JSON — returns None (can't parse)."""
    result = council.parse_chairman_json('{"final_answer": "truncated...')
    assert result is None


# ── Full Pipeline Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_mock():
    """End-to-end pipeline with mocked API responses."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content)

        # Chairman call (last one, uses GPT-4o)
        if body["model"] == council.CHAIRMAN["model"]:
            return httpx.Response(200, json=mock_openrouter_success(MOCK_CHAIRMAN_JSON))
        # All other calls (councilors)
        return httpx.Response(200, json=mock_openrouter_success())

    # Set API key for the test
    council.OPENROUTER_API_KEY = "sk-or-v1-test-key"

    with respx.mock:
        respx.post(council.OPENROUTER_API_URL).mock(side_effect=side_effect)
        result = await council.run_council("Should I use Go or Python?")

    # Verify output structure
    assert result["question"] == "Should I use Go or Python?"
    assert "final_answer" in result
    assert isinstance(result["disagreements"], list)
    assert isinstance(result["consensus_points"], list)
    assert result["confidence"] in ("high", "medium", "low", "unknown")
    assert len(result["individual_answers"]) == 4
    assert len(result["peer_reviews"]) == 4
    assert result["chairman"] == council.CHAIRMAN["label"]
    assert isinstance(result["council"], list)
    assert result["stage2_skipped"] is False
    assert "run_started_at" in result
    assert "run_duration_seconds" in result
    assert isinstance(result["errors"], list)

    # Should have made 9 API calls: 4 answers + 4 reviews + 1 chairman
    assert call_count == 9


@pytest.mark.asyncio
async def test_fast_mode():
    """--fast skips Stage 2, only 5 API calls."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content)

        if body["model"] == council.CHAIRMAN["model"]:
            return httpx.Response(200, json=mock_openrouter_success(MOCK_CHAIRMAN_JSON))
        return httpx.Response(200, json=mock_openrouter_success())

    council.OPENROUTER_API_KEY = "sk-or-v1-test-key"

    with respx.mock:
        respx.post(council.OPENROUTER_API_URL).mock(side_effect=side_effect)
        result = await council.run_council("Quick question?", fast=True)

    assert result["stage2_skipped"] is True
    assert result["peer_reviews"] == []
    # Should have made 5 API calls: 4 answers + 1 chairman (no reviews)
    assert call_count == 5


# ── Retry Logic Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_on_429():
    """429 rate limit triggers retry, succeeds on second attempt."""
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, headers={"Retry-After": "0.1"}, text="Rate limited")
        return httpx.Response(200, json=mock_openrouter_success())

    with respx.mock:
        respx.post(council.OPENROUTER_API_URL).mock(side_effect=side_effect)
        async with httpx.AsyncClient() as client:
            ok, content = await council.call_model(client, "test/model:free", [{"role": "user", "content": "hi"}], "Test")

    assert ok is True
    assert content == MOCK_ANSWER
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted():
    """All retries fail — returns error tuple."""
    with respx.mock:
        respx.post(council.OPENROUTER_API_URL).respond(500, text="Server Error")
        async with httpx.AsyncClient() as client:
            ok, content = await council.call_model(client, "test/model:free", [{"role": "user", "content": "hi"}], "Test")

    assert ok is False
    assert "Test" in content
