# MEMORY.md — LLM Council

Running log of decisions, context, and discoveries. Update this as you work.

---

## Origin

Built as an OpenClaw skill inspired by karpathy/llm-council (abandoned Saturday
hack, 9.8k stars). Core insight: the user was already manually bouncing questions
between Claude and ChatGPT — this automates that workflow and adds structure.

Designed for personal use first, share to ClawHub if it provides value.

---

## Key Decisions

### Why OpenRouter instead of direct provider APIs?
Single API key, single endpoint, unified billing. Free models across providers
without managing 4+ API keys. Simplifies the Docker setup significantly.

### Why free councilors + paid Chairman?
Councilors provide diversity of thought at zero cost. The Chairman (GPT-4o) is
the bottleneck — it synthesizes 8+ inputs into structured JSON, which needs the
most capability. One paid call at ~$0.02/query is worth it for reliable synthesis.

### Why GPT-4o as Chairman?
Strong at structured JSON output (critical for the Chairman role). Fast, reliable,
well-priced. Selected over Claude Sonnet to avoid self-selection bias.

### Why these 4 councilors?
Selected for cognitive diversity — different reasoning patterns, not just different
companies:
- **DeepSeek R1** — Chain-of-thought reasoner. Breaks problems into steps. Finds
  logical flaws others miss. Genuinely different reasoning approach.
- **Hermes 3 405B** — 405B params, the biggest free model. NousResearch fine-tune
  with diverse, high-quality training data. Deep knowledge, good at nuance.
- **Qwen3 Coder 480B** — Code-trained 480B MoE model. Thinks in structured,
  systematic patterns. Approaches questions from an engineering/systems angle.
- **Llama 3.3 70B** — Meta's solid general-purpose model. Practical advice,
  mainstream perspective. The "sensible center" of the council.

Diversity of cognitive approach > diversity of company origin.

### Why NOT Perplexity Sonar Pro as Chairman?
Investigated this. The Perplexity API only exposes the Sonar family (Llama-based
with web search). It does NOT expose GPT, Claude, Gemini, or Grok through the API
— that's only available in the consumer Perplexity Pro UI. GPT-4o is a better
Chairman at ~$0.02/query.

### Why ReportLab for PDF?
Official skill docs recommended it. Single dependency, no system packages needed,
good Python API for structured documents. weasyprint requires wkhtmltopdf system
dep which complicates Docker.

### Why custom Dockerfile vs setupCommand?
Python + pip deps are substantial. `setupCommand` runs per-container-creation
which adds latency to every session. Baking into the image means instant cold
start. Worth the extra deploy step.

### Why pipe architecture (council.py | council_pdf.py)?
Separation of concerns. council.py can be used standalone (pipe to jq, save JSON,
etc). council_pdf.py can render any valid council JSON. Keeps both scripts focused
and independently useful.

---

## Architecture Notes

### Error handling approach
- `call_model()` returns `(success: bool, content: str)` tuples
- Failed models are filtered out, not passed downstream as fake answers
- Minimum quorum: 2 successful councilors required or pipeline fails loudly
- Retries: up to 2 retries on 429/5xx with exponential backoff
- All errors tracked in output JSON `errors` array

### Stage 2 anonymization approach
Each reviewer gets the other answers shuffled randomly and labeled Model A/B/C.
The reviewer's own answer is excluded. Shuffle is per-reviewer so even if one
reviewer figures out positional patterns, another reviewer sees a different order.

### Chairman JSON parsing
Three-strategy approach: direct parse, markdown fence extraction (regex), and
outermost brace matching. Raw response is logged to stderr before parse attempt.
Parsed result is validated for required keys and correct types.

### PDF safety
All user-sourced text is XML-escaped via `xml_escape()` before passing to
ReportLab `Paragraph()`. This prevents crashes on `&`, `<`, `>` in LLM output.
Input is validated and coerced in `validate_input()` before rendering.

### PDF delivery in OpenClaw
The PDF is written to the OpenClaw workspace directory
(`/home/openclaw/workspace/`). OpenClaw's file-send tool then delivers it to the
user's chat app as a file attachment. The SKILL.md instructs the agent to do this
automatically.

---

## What Claude Code Should Know

### Don't change
- The 3-stage pipeline structure
- ReportLab as the PDF library
- SKILL.md frontmatter format (AgentSkills spec)
- The pipe architecture between the two scripts
- GPT-4o as Chairman (user's explicit choice)

### Could improve
- Markdown-to-ReportLab rendering (currently `split("\n\n")` loses bullet lists, code blocks)
- Progress messages to chat during long runs
- `--grounded` flag swapping Chairman to Perplexity Sonar for web-grounded synthesis

---

## Rate Limit Math

Free tier (councilors): 200 req/day, 20 req/min
Per council run: 4 (answers) + 4 (reviews) + 1 (chairman) = 9 requests (8 free + 1 paid)
Queries per day: floor(200 / 8) = 25 (limited by free councilor calls)
Fast mode: 4 (answers) + 1 (chairman) = 5 requests (4 free + 1 paid)
Fast mode queries per day: floor(200 / 4) = 50
Safe burst: 2 council queries per minute (16 free req/min, under the 20/min cap)

---

## Resolved Issues

| Issue | Resolution |
|-------|------------|
| XML chars crash ReportLab Paragraph() | Added `xml_escape()` helper, applied to all user text |
| Chairman malformed JSON fallback is weak | 3-strategy parser: direct, fence extraction, brace match |
| Single councilor failure kills pipeline | Error tuples + quorum check (min 2) |
| 429 rate limits not retried | Exponential backoff with up to 2 retries |
| PDF filename is timestamp-only | Added slugify() for `council_{ts}_{slug}.pdf` |
| No test coverage | Full test suite in tests/ |
| Councilor lineup lacked cognitive diversity | Replaced with role-based selection (reasoner, knowledge, structuralist, generalist) |
| Chairman was free DeepSeek V3 | Upgraded to paid GPT-4o for reliable synthesis |
| setup.sh didn't validate API key | Added `sk-or-v1-` prefix validation |
| setup.sh skipped existing openclaw.json | Now merges council skill into existing config |
| setup.sh had no update mode | Added `--update` flag |

---

## Future Directions (Out of Scope for Now)

- **Prestige council**: Claude + GPT-4o + Gemini + Grok as paid councilors,
  Perplexity Sonar Pro as Chairman for web-grounded synthesis. ~$0.25-0.35/query.
- **ClawHub publish**: If personal testing confirms value, package for the
  OpenClaw skill registry.
- **`/council-fast`**: Already implemented as `--fast` flag.
- **Scheduled councils**: Cron job that runs a council on a recurring question
  and diffs the answers over time.
- **Markdown rendering**: Replace naive `split("\n\n")` with proper Markdown-to-ReportLab conversion.
