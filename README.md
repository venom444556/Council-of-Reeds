# Council of Reeds

**A multi-LLM deliberation engine.** Ask a question, get answers from 4 AI models with different cognitive strengths, have them anonymously review each other, then a Kimi K2.5 Chairman synthesizes the best final answer with a full disagreement breakdown. **100% free.**

Inspired by [karpathy/llm-council](https://github.com/karpathy/llm-council). Rebuilt as a deployable tool with error handling, retry logic, and PDF report generation.

---

## How It Works

```
Your question
     |
     v
Stage 1 — Four models answer independently (parallel)
     |
     v
Stage 2 — Each model reviews the others anonymously (Model A/B/C)
     |
     v
Stage 3 — Kimi K2.5 Chairman synthesizes everything into a final answer
     |
     v
Structured JSON + styled PDF report
```

**Stage 1** fires your question to 4 free models simultaneously. Each brings a different cognitive lens — a chain-of-thought reasoner, a deep knowledge model, a structured/systems thinker, and a practical generalist.

**Stage 2** gives each model the other three answers, shuffled and anonymized. They rank them, identify contradictions, and call out what each got right or missed. This surfaces disagreements the Chairman needs to adjudicate.

**Stage 3** sends everything to Kimi K2.5 — a trillion-parameter MoE model that matches GPT-5.2 and Claude Opus 4.5 on benchmarks. It gets all answers with real names, plus all anonymous reviews. It synthesizes a definitive answer, lists where the models agreed, and breaks down every disagreement with a verdict.

## The Council

| Role | Model | Cognitive Strength |
|------|-------|--------------------|
| Councilor | DeepSeek R1 | **Reasoner** — chain-of-thought, step-by-step logic |
| Councilor | Hermes 3 405B | **Knowledge** — 405B params, deep and nuanced |
| Councilor | Qwen3 Coder 480B | **Structuralist** — systems thinking, engineering angle |
| Councilor | Llama 3.3 70B | **Generalist** — practical, mainstream perspective |
| Chairman | Kimi K2.5 | **Synthesizer** — trillion-param MoE, top-tier benchmarks |

All models are free via OpenRouter. **$0.00/query.**

## Quick Start

```bash
# 1. Get an OpenRouter API key (free tier — all models are free)
#    https://openrouter.ai

# 2. Set your key
export OPENROUTER_API_KEY=sk-or-v1-...

# 3. Install dependencies
pip install httpx reportlab

# 4. Run a council
python3 council.py "Should I build my startup in Go or Python?"

# 5. Generate a PDF report
python3 council.py "Should I build my startup in Go or Python?" | \
  python3 council_pdf.py --output report.pdf
```

### Fast Mode

Skip Stage 2 (cross-review) for faster results. 5 API calls instead of 9.

```bash
python3 council.py --fast "Quick take on Postgres vs MongoDB?" | \
  python3 council_pdf.py --output report.pdf
```

## Output

The council returns structured JSON:

```json
{
  "question": "Should I build my startup in Go or Python?",
  "final_answer": "Python for most startups. Here's why...",
  "disagreements": [
    {
      "topic": "Performance at scale",
      "summary": "Qwen3 argued Go's concurrency matters early...",
      "chairman_verdict": "At startup scale, dev speed beats runtime speed."
    }
  ],
  "consensus_points": [
    "Both are production-ready",
    "Team expertise should be a major factor"
  ],
  "confidence": "high",
  "confidence_note": "Strong alignment across all councilors."
}
```

The PDF report includes a cover page, confidence badge, the synthesized answer, disagreement cards with Chairman verdicts, council composition table, and an appendix with every raw model answer.

## Deploy with OpenClaw

Council of Reeds is built as an [OpenClaw](https://openclaw.ai) skill. One-click deploy to a server, then trigger from Telegram, WhatsApp, or Discord:

```bash
# One-click deploy
chmod +x setup.sh && ./setup.sh

# Then from your chat app:
/council Should we pivot from B2B to B2C?
```

See `setup.sh --update` to update an existing installation.

## Cost

| Component | Cost |
|-----------|------|
| 4 councilor calls | Free (OpenRouter free tier) |
| 1 Chairman call (Kimi K2.5) | Free (OpenRouter free tier) |
| **Total per query** | **$0.00** |

Free tier allows ~22 council queries/day (40 in fast mode).

## Testing

```bash
pip install pytest pytest-asyncio respx
pytest tests/ -v --asyncio-mode=auto
```

Tests mock all OpenRouter calls — no API key needed, no real requests made.

## Project Structure

```
council.py           3-stage async pipeline
council_pdf.py       ReportLab PDF renderer
SKILL.md             OpenClaw skill definition
Dockerfile           Docker image (extends openclaw/openclaw:latest)
docker-compose.yml   Service composition
setup.sh             One-click server deploy
tests/
  test_council.py    Pipeline tests (13 tests)
  test_pdf.py        PDF renderer tests (20 tests)
```

## Credits

Inspired by [karpathy/llm-council](https://github.com/karpathy/llm-council) — a Saturday hack by Andrej Karpathy that demonstrated the multi-model deliberation concept. We took the idea and rebuilt it as a deployable, production-hardened tool with free model accessibility, error resilience, and PDF reporting.

## License

MIT
