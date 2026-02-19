---
name: council
description: Runs your question through a multi-LLM council. 4 free models answer independently, review each other anonymously, then a Kimi K2.5 Chairman synthesizes the best final answer with a disagreement breakdown. 100% free. Trigger with /council [your question].
metadata: {"openclaw":{"emoji":"⚖️","requires":{"env":["OPENROUTER_API_KEY"]},"primaryEnv":"OPENROUTER_API_KEY"}}
user-invocable: true
---

# LLM Council Skill

When the user invokes `/council [question]` or asks you to "run this through the council", use this skill.

## What This Skill Does

Runs a 3-stage deliberation across 5 models via OpenRouter:

1. **Stage 1 – First Opinions**: 4 free councilor models answer the question independently and in parallel
2. **Stage 2 – Anonymous Cross-Review**: Each model reviews the other answers (anonymized as Model A/B/C) and ranks them
3. **Stage 3 – Chairman Synthesis**: Kimi K2.5 (free) reads all answers + reviews and produces a final synthesized response plus a disagreement breakdown

## How to Invoke

**Text response + PDF report (default behavior):**
```bash
python3 {baseDir}/council.py "[THE USER'S QUESTION]" | python3 {baseDir}/council_pdf.py --output /home/openclaw/workspace/council_report.pdf
```

**Fast mode (skip cross-review, faster + cheaper):**
```bash
python3 {baseDir}/council.py --fast "[THE USER'S QUESTION]" | python3 {baseDir}/council_pdf.py --output /home/openclaw/workspace/council_report.pdf
```

**Text response only:**
```bash
python3 {baseDir}/council.py "[THE USER'S QUESTION]"
```

Replace `[THE USER'S QUESTION]` with the user's actual question, properly shell-escaped (escape single quotes, double quotes, backticks).

The script requires `OPENROUTER_API_KEY` to be set in the environment.

## Output

`council.py` outputs JSON with:
- `final_answer`: The Chairman's synthesized response
- `disagreements`: Where models disagreed and why it matters
- `consensus_points`: What all models agreed on
- `confidence`: high / medium / low
- `individual_answers`: Each councilor's raw answer
- `errors`: Any models that failed (pipeline continues if 2+ succeed)
- `stage2_skipped`: Whether fast mode was used

`council_pdf.py` takes that JSON and produces a styled PDF with:
- Cover block with timestamp
- The question (highlighted)
- Confidence badge
- Chairman's final answer
- Consensus points
- Disagreement cards with Chairman verdicts
- Council composition table
- Appendix: all individual model answers

Always generate the PDF by default when the user uses `/council`. Workflow:
1. Run council.py piped into council_pdf.py, saving to the workspace
2. Present the `final_answer` and `disagreements` summary in chat
3. Use the file-send tool to deliver the PDF directly to the user in their chat app

If the user says "quick" or "fast", use `--fast` to skip Stage 2.

## Council Lineup

| Role | Model | Cognitive Role |
|------|-------|---------------|
| Councilor 1 | deepseek/deepseek-r1-0528:free | Reasoner (chain-of-thought) |
| Councilor 2 | nousresearch/hermes-3-llama-3.1-405b:free | Knowledge (405B deep knowledge) |
| Councilor 3 | qwen/qwen3-coder:free | Structuralist (systems thinking) |
| Councilor 4 | meta-llama/llama-3.3-70b-instruct:free | Generalist (practical advice) |
| Chairman | moonshotai/kimi-k2.5:free | Synthesizer (free, trillion-param MoE) |

## Cost

- Councilor calls: Free (OpenRouter free tier)
- Chairman call: Free (Kimi K2.5 via OpenRouter free tier)
- Total per /council run: **$0.00**

## Rate Limits

Free tier: 200 requests/day, 20/min.
Each council run uses 9 free calls (4 answers + 4 reviews + 1 chairman).
That's ~22 council queries/day on the free tier.
Fast mode: 5 free calls total (~40 queries/day on free tier).

## Config (openclaw.json)

```json
{
  "skills": {
    "entries": {
      "council": {
        "enabled": true,
        "env": {
          "OPENROUTER_API_KEY": "YOUR_OPENROUTER_KEY_HERE"
        }
      }
    }
  }
}
```
