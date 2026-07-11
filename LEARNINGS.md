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

## [2026-07-11] — v4 Agent Theatre (watch real runs, don't build pipelines)

**What worked:**
- Developing the transcript adapter against a *real* Claude Code session file (the very session doing the work) instead of guessing the format from memory — it immediately surfaced two non-obvious facts: token `usage` repeats across transcript lines sharing a `requestId` (must dedupe or you double-count), and lines include bookkeeping types (`queue-operation`, `attachment`, `last-prompt`) that must be skipped.
- Keeping the pivot an *event-source swap*: the v3 event vocabulary (`node_started`/`edge_fired`/…) generalized almost 1:1 to real-run events, so the theatre is a new renderer over a normalized stream, not a rewrite.
- A generated (script-produced) demo transcript in the real format doubles as test fixture and zero-setup demo, and can be regenerated when the story needs to change.
- "Pixel characters, smooth stage": keeping sprites crunchy but making edges/glows/panels antialiased answered the "pixel art is clunky" critique without losing the mascot charm.

**What didn't work:**
- Sorting transcript records by timestamp *string*: `"…45.5Z"` sorts before `"…45Z"`, which processed a tool result before its tool call and silently mis-attributed subagent work. Parse timestamps before sorting, always.
- CSS state classes with different lifetimes in one `classList.remove(...)` call — clearing `working/thinking` also wiped the sticky `retired` fade. Sticky states need separate management.

**For next time:**
- Screenshot-test new frontends with Playwright before calling them done — both bugs above were caught by *looking at* the rendered stage, not by pytest.
- Live hook payloads carry no agent identity; note attribution heuristics as caveats in docs rather than pretending precision.

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
