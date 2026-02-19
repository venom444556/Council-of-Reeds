"""Tests for council_pdf.py — PDF report renderer."""

import json
import os
import shutil
import pytest
import tempfile

# Adjust path so we can import from parent
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import council_pdf


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_COUNCIL_JSON = {
    "question": "Build a SaaS analytics platform for small businesses",
    "executive_summary": "A phased approach to building a SaaS analytics platform is recommended. Start with a focused MVP targeting a single vertical, validate product-market fit, then expand. The key strategic advantage is simplicity — most competitors over-serve enterprise customers, leaving small businesses underserved.",
    "deliverables": [
        {
            "name": "Market Validation Report",
            "description": "Customer interviews, competitor analysis, and demand signal assessment.",
            "phase": "Phase 1"
        },
        {
            "name": "MVP Analytics Dashboard",
            "description": "Core dashboard with 3-5 key metrics for a single vertical.",
            "phase": "Phase 2"
        }
    ],
    "success_criteria": [
        {
            "metric": "Customer interview completion",
            "target": "20+ interviews in target vertical",
            "rationale": "Sufficient sample to identify patterns in needs and willingness to pay."
        },
        {
            "metric": "MVP trial conversion",
            "target": "15% of trial users convert to paid within 30 days",
            "rationale": "Industry benchmark for B2B SaaS at early stage."
        }
    ],
    "phases": [
        {
            "name": "Phase 1: Discovery",
            "duration": "3-4 weeks",
            "objectives": ["Complete customer interviews", "Map competitive landscape", "Define MVP scope"],
            "decision_point": "Evidence of willingness to pay from 5+ potential customers"
        },
        {
            "name": "Phase 2: Build MVP",
            "duration": "6-8 weeks",
            "objectives": ["Build core dashboard", "Onboard 10 beta users", "Establish feedback loop"],
            "decision_point": "3+ beta users actively using product weekly"
        }
    ],
    "risks": [
        {
            "risk": "Small business churn rate too high to sustain",
            "severity": "high",
            "mitigation": "Focus on vertical with highest retention patterns; build annual pricing incentives."
        },
        {
            "risk": "Feature creep during MVP phase",
            "severity": "medium",
            "mitigation": "Strict 5-metric cap for MVP dashboard; maintain a backlog but defer."
        }
    ],
    "moats": [
        {
            "type": "Data Advantage",
            "description": "Aggregated anonymized benchmarks from SMB customers create unique industry insights.",
            "durability": "Strong — compounds with each new customer and cannot be replicated without equivalent user base."
        },
        {
            "type": "Switching Cost",
            "description": "Historical data and custom dashboards create stickiness once onboarded.",
            "durability": "Moderate — grows stronger over time as data history accumulates."
        }
    ],
    "strategic_priorities": [
        "Validate demand before building",
        "Focus on one vertical before expanding",
        "Keep MVP scope ruthlessly small"
    ],
    "resource_considerations": "Requires 2 developers and 1 designer for MVP. Founder should lead customer interviews. Budget for 4-6 months of runway before revenue.",
    "go_no_go_criteria": [
        "At least 5 potential customers express willingness to pay",
        "Clear vertical identified with accessible customer base",
        "Team capacity confirmed for 6-8 week build cycle"
    ],
    "disagreements": [
        {
            "topic": "Single vertical vs. horizontal launch",
            "summary": "Some advisors recommended launching horizontally to maximize addressable market, while others argued for vertical focus.",
            "chairman_verdict": "Vertical focus is the stronger strategy at this stage. Horizontal expansion can follow once the core value proposition is proven."
        }
    ],
    "confidence": "high",
    "confidence_note": "Strong alignment across all advisors on the phased, validation-first approach.",
    "individual_answers": [
        {"model": "DeepSeek R1", "answer": "A step-by-step strategic analysis of the SaaS opportunity..."},
        {"model": "Hermes 3 405B", "answer": "The market dynamics for small business analytics suggest..."},
        {"model": "Qwen3 Coder 480B", "answer": "From a systems perspective, the platform strategy should..."},
        {"model": "Llama 3.3 70B", "answer": "For a practical launch strategy, focus on validation first..."},
    ],
    "peer_reviews": [
        {"reviewer": "DeepSeek R1", "review": "Model A had the strongest risk analysis, Model B lacked decision criteria."},
        {"reviewer": "Hermes 3 405B", "review": "Model A was thorough on phases, Model C drifted into implementation details."},
    ],
    "chairman": "Kimi K2.5 (Chairman)",
    "council": ["DeepSeek R1", "Hermes 3 405B", "Qwen3 Coder 480B", "Llama 3.3 70B"],
    "stage2_skipped": False,
    "run_started_at": "2026-02-18T12:00:00+00:00",
    "run_duration_seconds": 45.2,
    "errors": [],
}


# ── Helper ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def cleanup_temp_dirs():
    """Track and clean up all temp directories created during a test."""
    created = []
    original_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        d = original_mkdtemp(*args, **kwargs)
        created.append(d)
        return d

    tempfile.mkdtemp = tracking_mkdtemp
    yield
    tempfile.mkdtemp = original_mkdtemp
    for d in created:
        shutil.rmtree(d, ignore_errors=True)


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


def test_pdf_special_chars_in_summary():
    """Executive summary with XML special characters renders cleanly."""
    data = {**VALID_COUNCIL_JSON, "executive_summary": "Use <script> tags & escape them with &amp; entities. Compare x > y."}
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


def test_pdf_special_chars_in_priorities():
    """Strategic priorities with XML chars don't crash."""
    data = {**VALID_COUNCIL_JSON, "strategic_priorities": [
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


def test_pdf_empty_priorities():
    """Empty strategic_priorities array renders without crash."""
    data = {**VALID_COUNCIL_JSON, "strategic_priorities": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_empty_individual_answers():
    """Empty individual_answers skips appendix without crash."""
    data = {**VALID_COUNCIL_JSON, "individual_answers": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_long_summary():
    """3000+ word executive_summary doesn't crash or exceed memory."""
    long_text = "This is a very detailed strategic analysis. " * 500  # ~3500 words
    data = {**VALID_COUNCIL_JSON, "executive_summary": long_text}
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
    """Non-list fields get coerced to empty list."""
    data = {
        "question": "Test?",
        "disagreements": "not a list",
        "strategic_priorities": None,
        "deliverables": 123,
        "council": 123,
        "individual_answers": "also not a list",
    }
    cleaned = council_pdf.validate_input(data)
    assert cleaned["disagreements"] == []
    assert cleaned["strategic_priorities"] == []
    assert cleaned["deliverables"] == []
    assert cleaned["council"] == []
    assert cleaned["individual_answers"] == []


def test_validate_input_preserves_valid():
    """Valid data passes through unchanged."""
    cleaned = council_pdf.validate_input(VALID_COUNCIL_JSON)
    assert cleaned["question"] == VALID_COUNCIL_JSON["question"]
    assert cleaned["executive_summary"] == VALID_COUNCIL_JSON["executive_summary"]
    assert len(cleaned["disagreements"]) == 1
    assert len(cleaned["strategic_priorities"]) == 3
    assert len(cleaned["deliverables"]) == 2
    assert len(cleaned["phases"]) == 2
    assert len(cleaned["risks"]) == 2
    assert len(cleaned["moats"]) == 2


def test_validate_input_missing_fields():
    """Missing fields get sensible defaults."""
    cleaned = council_pdf.validate_input({})
    assert cleaned["question"] == "Unknown question"
    assert cleaned["executive_summary"] == "No strategic plan provided."
    assert cleaned["confidence"] == "unknown"
    assert cleaned["chairman"] == "Unknown"
    assert cleaned["resource_considerations"] == ""
    assert cleaned["deliverables"] == []
    assert cleaned["phases"] == []
    assert cleaned["moats"] == []


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


# ── New Section Edge Case Tests ──────────────────────────────────────────────

def test_pdf_empty_deliverables():
    """Empty deliverables array renders without crash."""
    data = {**VALID_COUNCIL_JSON, "deliverables": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_empty_phases():
    """Empty phases array renders without crash."""
    data = {**VALID_COUNCIL_JSON, "phases": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_empty_risks():
    """Empty risks array renders without crash."""
    data = {**VALID_COUNCIL_JSON, "risks": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_empty_success_criteria():
    """Empty success_criteria array renders without crash."""
    data = {**VALID_COUNCIL_JSON, "success_criteria": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_empty_moats():
    """Empty moats array renders without crash."""
    data = {**VALID_COUNCIL_JSON, "moats": []}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_special_chars_in_deliverables():
    """Deliverables with XML chars don't crash."""
    data = {**VALID_COUNCIL_JSON, "deliverables": [
        {
            "name": "MVP for <Product> & Integration",
            "description": "Build the core features & ensure x < y > z compatibility.",
            "phase": "Phase 1"
        }
    ]}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_special_chars_in_risks():
    """Risks with XML chars don't crash."""
    data = {**VALID_COUNCIL_JSON, "risks": [
        {
            "risk": "Competitor <X> & partner Y might launch first",
            "severity": "high",
            "mitigation": "Monitor competitor <activity> & accelerate timeline."
        }
    ]}
    path = generate_pdf(data)
    assert os.path.exists(path)


def test_pdf_special_chars_in_moats():
    """Moats with XML chars don't crash."""
    data = {**VALID_COUNCIL_JSON, "moats": [
        {
            "type": "Data & Network <Effect>",
            "description": "Users generate data that improves the platform & creates > value.",
            "durability": "Strong — grows with scale & is hard to replicate."
        }
    ]}
    path = generate_pdf(data)
    assert os.path.exists(path)
