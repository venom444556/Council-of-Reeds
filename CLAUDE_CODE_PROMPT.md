# LLM Council — Claude Code Handoff

## What This Is

A multi-LLM deliberation skill for OpenClaw. Users trigger `/council [question]`
from Telegram/WhatsApp/Discord. The skill fires the question to 4 free models in
parallel via OpenRouter, runs anonymous cross-review between them, then a GPT-4o
Chairman synthesizes a final answer + disagreement breakdown. Output is delivered
in chat AND as a formatted PDF report.

## File Structure

```
council/
  SKILL.md          <- OpenClaw skill definition (tells the agent how to invoke)
  council.py        <- 3-stage orchestration (Stage 1: answers, Stage 2: reviews, Stage 3: synthesis)
  council_pdf.py    <- ReportLab PDF renderer (takes council.py JSON output)
  Dockerfile        <- Extends openclaw/openclaw:latest with Python + httpx + reportlab
  docker-compose.yml
  setup.sh          <- One-click server deploy script (supports --update flag)
  CLAUDE_CODE_PROMPT.md
  CLAUDE.md
  MEMORY.md
  tests/
    test_council.py
    test_pdf.py
```

## Council Lineup

| Role       | Model                                          | Cognitive Role |
|------------|------------------------------------------------|---------------|
| Councilor  | deepseek/deepseek-r1-0528:free                 | Reasoner      |
| Councilor  | nousresearch/hermes-3-llama-3.1-405b:free      | Knowledge     |
| Councilor  | qwen/qwen3-coder:free                          | Structuralist |
| Councilor  | meta-llama/llama-3.3-70b-instruct:free         | Generalist    |
| Chairman   | openai/gpt-4o (paid)                           | Synthesizer   |

All councilor calls go through OpenRouter free tier. Chairman call is paid (~$0.02/query).

## Environment

- Python 3.10+
- Dependencies: `httpx`, `reportlab`
- OpenRouter API key required (set as `OPENROUTER_API_KEY` env var, must start with `sk-or-v1-`)
- For tests: mock the OpenRouter API, don't make real calls
- Test framework: `pytest` + `pytest-asyncio` + `respx` for async mocking

## Key Constraints

- **Councilors must be free** (`:free` suffix on OpenRouter). Do not swap to paid models.
- **Chairman is paid** (GPT-4o). Do not downgrade to a free model.
- **No new infrastructure dependencies** — keep it Python-only, no Redis, no DB.
- **PDF must be self-contained** — single file output, no external assets.
- **OpenClaw skill format** — SKILL.md must stay AgentSkills-compatible with
  valid YAML frontmatter. Don't break the metadata structure.
- **ReportLab only** — do not switch PDF libraries. No pypdf, no weasyprint.
- **Never use Unicode subscript/superscript chars in ReportLab** — use XML tags
  (`<sub>`, `<super>`) instead or they render as black boxes.
- **XML-escape all user content** — use `xml_escape()` helper before passing to `Paragraph()`.

## What Good Looks Like

After your work, running this end-to-end should work flawlessly:

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
python3 council.py "Should I build my startup in Go or Python?" | \
  python3 council_pdf.py --output test_report.pdf
```

And the PDF should handle any answer content without crashing.

Fast mode:
```bash
python3 council.py --fast "Quick take on Postgres vs MongoDB?" | \
  python3 council_pdf.py --output test_report.pdf
```

Tests should all pass:
```bash
pytest tests/ -v --asyncio-mode=auto
```
