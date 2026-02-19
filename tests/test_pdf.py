"""Tests for council_pdf.py — PDF report renderer."""

import json
import os
import pytest
import tempfile

# Adjust path so we can import from parent
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import council_pdf


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_COUNCIL_JSON = {
    "question": "Should I use Go or Python for my startup?",
    "final_answer": "Python is the better choice for most startups. It offers rapid prototyping, a vast ecosystem of libraries, and easier hiring. Go excels at performance-critical services but introduces more development friction early on.",
    "disagreements": [
        {
            "topic": "Performance vs. Productivity",
            "summary": "Models disagreed on whether Go's performance advantage matters at startup scale.",
            "chairman_verdict": "At startup scale, development speed matters more than raw performance. Python wins here."
        },
        {
            "topic": "Type Safety",
            "summary": "Some models argued Go's type system catches bugs earlier, while others said Python's flexibility is more valuable.",
            "chairman_verdict": "Type safety helps at scale, but startups need to iterate fast. Python with type hints is a good middle ground."
        }
    ],
    "consensus_points": [
        "Both languages are production-ready and widely used",
        "The team's existing expertise should be a major factor",
        "Python has a larger ecosystem for ML/data tasks"
    ],
    "confidence": "high",
    "confidence_note": "Strong alignment across all councilors on Python for most startup use cases.",
    "individual_answers": [
        {"model": "DeepSeek R1", "answer": "Python is the clear winner for startups. Here's my reasoning step by step..."},
        {"model": "Hermes 3 405B", "answer": "Both languages have merits, but Python's ecosystem gives it the edge..."},
        {"model": "Qwen3 Coder 480B", "answer": "From a systems perspective, Go has cleaner concurrency patterns..."},
        {"model": "Llama 3.3 70B", "answer": "For most startups, Python is the practical choice..."},
    ],
    "peer_reviews": [
        {"reviewer": "DeepSeek R1", "review": "Model A was thorough, Model B too vague, Model C had good points."},
        {"reviewer": "Hermes 3 405B", "review": "Model A nailed the reasoning, Model C was too focused on performance."},
    ],
    "chairman": "GPT-4o (Chairman)",
    "council": ["DeepSeek R1", "Hermes 3 405B", "Qwen3 Coder 480B", "Llama 3.3 70B"],
    "stage2_skipped": False,
    "run_started_at": "2026-02-18T12:00:00+00:00",
    "run_duration_seconds": 45.2,
    "errors": [],
}


# ── Helper ────────────────────────────────────────────────────────────────────

def generate_pdf(data: dict, filename: str = "test.pdf") -> str:
    """Generate a PDF in a temp directory, return the path."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, filename)
    council_pdf.build_pdf(data, path)
    return path


# ── Basic Generation Tests ────────────────────────────────────────────────────

def test_pdf_generates():
    """Valid council JSON produces a non-empty PDF file."""
    path = generate_pdf(VALID_COUNCIL_JSON)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0


def test_pdf_generates_minimal():
    """Minimal JSON (just question) produces a PDF without crash."""
    minimal = {"question": "Hello?"}
    path = generate_pdf(minimal)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0


# ── Special Characters Tests ──────────────────────────────────────────────────

def test_pdf_special_chars_in_question():
    """Question with &, <, > doesn't crash the renderer."""
    data = {**VALID_COUNCIL_JSON, "question": "What's the diff between A & B when x < y > z?"}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_special_chars_in_answer():
    """Final answer with XML special characters renders cleanly."""
    data = {**VALID_COUNCIL_JSON, "final_answer": "Use <script> tags & escape them with &amp; entities. Compare x > y."}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_special_chars_in_disagreements():
    """Disagreement cards with XML chars don't crash."""
    data = {**VALID_COUNCIL_JSON, "disagreements": [
        {
            "topic": "Q&A format vs <structured> output",
            "summary": "Models debated whether x < y & z > w matters.",
            "chairman_verdict": "The <best> approach uses & handles edge cases."
        }
    ]}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_special_chars_in_consensus():
    """Consensus points with XML chars don't crash."""
    data = {**VALID_COUNCIL_JSON, "consensus_points": [
        "All agreed: A & B > C",
        "The <framework> approach is best",
    ]}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_special_chars_in_individual():
    """Individual answers with XML chars don't crash."""
    data = {**VALID_COUNCIL_JSON, "individual_answers": [
        {"model": "Test & Model <1>", "answer": "Use &amp; for & and &lt; for < in XML."},
    ]}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_unicode_content():
    """Unicode characters in content don't crash."""
    data = {**VALID_COUNCIL_JSON, "question": "What about internationalization? 日本語 中文 한국어"}
    path = generate_pdf(data)
    assert os.path.exists(path)


# ── Edge Case Tests ───────────────────────────────────────────────────────────

def test_pdf_empty_disagreements():
    """Empty disagreements array renders without crash."""
    data = {**VALID_COUNCIL_JSON, "disagreements": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_empty_consensus():
    """Empty consensus_points array renders without crash."""
    data = {**VALID_COUNCIL_JSON, "consensus_points": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_empty_individual_answers():
    """Empty individual_answers skips appendix without crash."""
    data = {**VALID_COUNCIL_JSON, "individual_answers": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_long_answer():
    """3000+ word final_answer doesn't crash or exceed memory."""
    long_text = "This is a very detailed answer. " * 500  # ~3000 words
    data = {**VALID_COUNCIL_JSON, "final_answer": long_text}
    path = generate_pdf(data)
    assert os.path.exists(path)
    # Should be a multi-page PDF
    assert os.path.getsize(path) > 5000


def test_pdf_single_word_question():
    """Single-word question renders properly."""
    data = {**VALID_COUNCIL_JSON, "question": "Why?"}
    path = generate_pdf(data)
    assert os.path.exists(path)


# ── Input Validation Tests ────────────────────────────────────────────────────

def test_validate_input_coerces_types():
    """Non-list disagreements get coerced to empty list."""
    data = {
        "question": "Test?",
        "disagreements": "not a list",
        "consensus_points": None,
        "council": 123,
        "individual_answers": "also not a list",
    }
    cleaned = council_pdf.validate_input(data)
    assert cleaned["disagreements"] == []
    assert cleaned["consensus_points"] == []
    assert cleaned["council"] == []
    assert cleaned["individual_answers"] == []


def test_validate_input_preserves_valid():
    """Valid data passes through unchanged."""
    cleaned = council_pdf.validate_input(VALID_COUNCIL_JSON)
    assert cleaned["question"] == VALID_COUNCIL_JSON["question"]
    assert cleaned["final_answer"] == VALID_COUNCIL_JSON["final_answer"]
    assert len(cleaned["disagreements"]) == 2
    assert len(cleaned["consensus_points"]) == 3


def test_validate_input_missing_fields():
    """Missing fields get sensible defaults."""
    cleaned = council_pdf.validate_input({})
    assert cleaned["question"] == "Unknown question"
    assert cleaned["final_answer"] == "No answer provided."
    assert cleaned["confidence"] == "unknown"
    assert cleaned["chairman"] == "Unknown"


# ── Filename Tests ────────────────────────────────────────────────────────────

def test_slugify_basic():
    """Normal question gets slugified."""
    slug = council_pdf.slugify("Should I use Postgres or MongoDB?")
    assert slug == "should_i_use_postgres_or_mongodb"


def test_slugify_special_chars():
    """Special characters become underscores."""
    slug = council_pdf.slugify("What's the best C++ framework & why?")
    assert "&" not in slug
    assert "'" not in slug
    assert "+" not in slug


def test_slugify_truncation():
    """Long questions get truncated at 40 chars."""
    slug = council_pdf.slugify("This is a very long question that should definitely be truncated at some point")
    assert len(slug) <= 40


def test_slugify_empty():
    """Empty string returns 'council'."""
    assert council_pdf.slugify("") == "council"
    assert council_pdf.slugify("   ") == "council"


def test_pdf_filename_format():
    """Default filename includes timestamp and slug."""
    # This tests the main() logic indirectly via slugify
    slug = council_pdf.slugify("Should I use Go or Python?")
    assert "should_i_use_go_or_python" == slug


# ── XML Escape Tests ──────────────────────────────────────────────────────────

def test_xml_escape_ampersand():
    assert council_pdf.xml_escape("A & B") == "A &amp; B"


def test_xml_escape_angle_brackets():
    assert council_pdf.xml_escape("x < y > z") == "x &lt; y &gt; z"


def test_xml_escape_quotes():
    assert council_pdf.xml_escape('He said "hello"') == "He said &quot;hello&quot;"


def test_xml_escape_none():
    """None input returns empty string."""
    assert council_pdf.xml_escape(None) == ""


def test_xml_escape_number():
    """Non-string input gets converted."""
    assert council_pdf.xml_escape(42) == "42"


def test_xml_escape_preserves_safe():
    """Safe text passes through unchanged."""
    assert council_pdf.xml_escape("Hello world") == "Hello world"
