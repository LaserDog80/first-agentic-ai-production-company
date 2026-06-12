# LEARNINGS.md

> **Purpose:** Append-only log of insights from each coding challenge.  
> **Rule:** Only append new entries. Never delete or edit previous entries.

---

## How to Use This File

After completing each challenge, add an entry using this format:

```markdown
## [YYYY-MM-DD] — [Challenge Name]

**What worked:**
- [Insight]

**What didn't work:**
- [Insight]

**For next time:**
- [Actionable improvement]
```

---

## Entries

<!-- New entries go below this line, most recent first -->

## [2026-06-11] — v3 hardening pass (probe → fix everything)

**What worked:**
- Auditing before coding: a read-through of every live path surfaced a feature that was 100% broken in production (`/present` spoke a WebSocket protocol the server had dropped) and a semantic bug invisible to the test suite (the output edge was decorative — the executor always returned the entry agent's output).
- Encoding guardrails in two places: graph limits are rejected at validation time *and* clamped at execution time, so neither layer has to trust the other.
- Client-side replay: buffering the run's events in the browser gives a free "watch it again" demo feature with zero backend work.

**What didn't work:**
- Dead config is worse than no config: `agent_timeout_seconds` existed in config.yaml for months but was never passed to the runtime, so every reader assumed timeouts existed. Same for the search-depth settings.
- Keeping legacy modules "just in case" — ~2,200 lines (pixel-art renderers, the old orchestrator's prompts/schemas) were only reachable from their own tests, inflating the passing-test count while testing nothing real.

**For next time:**
- When an event protocol changes, grep every consumer (both HTML pages, not just the active one) before calling it done.
- Wire a config key to code in the same commit that adds it, or don't add it.
- Delete replaced code in the replacing PR; "later" never comes.
