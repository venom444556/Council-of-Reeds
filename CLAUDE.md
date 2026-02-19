# CLAUDE.md — LLM Council

## What This Project Is

A multi-LLM deliberation skill for OpenClaw. Fires a question to 4 free models
via OpenRouter in parallel, runs anonymous cross-review, then a paid GPT-4o
Chairman synthesizes a final answer + disagreement breakdown. Output: chat
summary + PDF report.

Triggered via `/council [question]` from Telegram, WhatsApp, Discord, or any
OpenClaw-connected chat app.

## Run Commands

```bash
# Full pipeline (answer + PDF)
export OPENROUTER_API_KEY=sk-or-v1-...
python3 council.py "Your question here" | python3 council_pdf.py --output report.pdf

# Fast mode (skip cross-review, 5 API calls instead of 9)
python3 council.py --fast "Your question here" | python3 council_pdf.py --output report.pdf

# Council only (JSON to stdout)
python3 council.py "Your question here"

# PDF from saved JSON
python3 council_pdf.py council_output.json --output report.pdf

# Tests
pytest tests/ -v --asyncio-mode=auto
```

## Project Structure

```
council/
  council.py          <- 3-stage pipeline (answers -> reviews -> synthesis)
  council_pdf.py      <- ReportLab PDF renderer
  SKILL.md            <- OpenClaw AgentSkills skill definition
  Dockerfile          <- Extends openclaw/openclaw:latest
  docker-compose.yml
  setup.sh            <- One-click server deploy (supports --update)
  CLAUDE_CODE_PROMPT.md
  CLAUDE.md           <- This file
  MEMORY.md           <- Project decisions + context
  tests/
    test_council.py
    test_pdf.py
```

## Architecture

```
User message (/council question)
        |
        v
  council.py
        |
        +-- Stage 1: asyncio.gather() -> 4 OpenRouter calls in parallel
        |   Each councilor answers independently
        |   Minimum quorum: 2 (fails loudly if fewer succeed)
        |
        +-- Stage 2: asyncio.gather() -> N review calls in parallel
        |   Each model reviews the OTHER answers (anonymized as Model A/B/C)
        |   Order shuffled per-reviewer to prevent position bias
        |   (Skipped with --fast flag)
        |
        +-- Stage 3: Chairman call (GPT-4o, paid)
            Gets all answers + reviews, returns structured JSON:
            { final_answer, disagreements[], consensus_points[],
              confidence, confidence_note }
        |
        v
  council_pdf.py (receives JSON via pipe or file)
        |
        +-- ReportLab -> PDF
            Cover -> Question -> Confidence badge -> Final answer
            -> Consensus -> Disagreement cards -> Council table
            -> Appendix (individual answers)
```

## Council Models

| Role      | Model                                      | OpenRouter ID                                  | Cognitive Role   |
|-----------|--------------------------------------------|------------------------------------------------|------------------|
| Councilor | DeepSeek R1                                | deepseek/deepseek-r1-0528:free                 | Reasoner         |
| Councilor | Hermes 3 405B                              | nousresearch/hermes-3-llama-3.1-405b:free      | Knowledge        |
| Councilor | Qwen3 Coder 480B                           | qwen/qwen3-coder:free                          | Structuralist    |
| Councilor | Llama 3.3 70B                              | meta-llama/llama-3.3-70b-instruct:free         | Generalist       |
| Chairman  | GPT-4o                                     | openai/gpt-4o                                  | Synthesizer      |

**Councilors are free. Chairman is paid (~$0.02/query).**

## API

All calls go to `https://openrouter.ai/api/v1/chat/completions`.
OpenAI-compatible. Auth: `Authorization: Bearer $OPENROUTER_API_KEY`.
Free tier limits (councilors): 200 req/day, 20 req/min.
Chairman (GPT-4o): rate limited by OpenRouter account credits.
Each `/council` run = ~9 API calls (5 in --fast mode).

## Hard Constraints

- **Free councilors only** — no paid model IDs for councilors
- **Paid Chairman** — GPT-4o for reliable synthesis + JSON output
- **Python only** — no new infrastructure (no Redis, no DB, no message queues)
- **ReportLab only** — do not switch PDF libraries (no weasyprint, no pypdf for generation)
- **Single-file PDF output** — no external assets, fonts, or images
- **AgentSkills format** — SKILL.md YAML frontmatter must stay valid
- **No Unicode subscripts/superscripts in ReportLab** — use `<sub>`/`<super>` XML tags or adjust font manually
- **XML-escape all user content** before passing to ReportLab `Paragraph()` — use `xml_escape()` helper

## Error Handling

- `call_model()` returns `(success: bool, content: str)` tuples
- Retries on 429/5xx with exponential backoff (up to 2 retries)
- Stage 1 requires minimum 2 successful councilors (quorum check)
- Failed models are tracked in `errors` array in output JSON
- Chairman JSON parsing uses 3 strategies: direct parse, markdown fence extraction, brace matching
- All errors logged to stderr with model name

## Testing Approach

- Mock all OpenRouter HTTP calls — never hit real API in tests
- Use `pytest-asyncio` for async test cases
- `respx` for mocking `httpx.AsyncClient`
- Tests live in `tests/` directory
- Coverage:
  - `council.py`: pipeline stages, partial failure, quorum, JSON parsing, fast mode, retries
  - `council_pdf.py`: generation, XML escaping, edge cases, validation, slugify

## Environment Variables

| Variable              | Required | Description                    |
|-----------------------|----------|--------------------------------|
| `OPENROUTER_API_KEY`  | Yes      | OpenRouter API key (sk-or-v1-) |

## Dependencies

```
httpx        # async HTTP client for OpenRouter calls
reportlab    # PDF generation
pytest       # test runner
pytest-asyncio  # async test support
respx        # httpx mock for tests
```

Install: `pip install httpx reportlab pytest pytest-asyncio respx`
