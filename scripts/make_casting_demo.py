"""Generate the 'THE CASTING' demo transcript for the Theatre.

Writes ``static/demo/the_casting_run.jsonl`` — a stage-ready cut of a *real*
agentic run (3 July 2026) that developed an unscripted TV format end to end.

The original run used the Workflow orchestrator, so its team lived in separate
``subagents/workflows/*`` files the theatre adapter never folds in — on stage it
looked like one lonely agent making a single opaque ``Workflow`` call. This cut
re-expresses that same run in the shape the adapter *does* render: each teammate
is a ``Task`` spawn with a matching ``isSidechain`` chain, so the whole cast
assembles itself on stage:

    Series Producer  →  Trend Scout  →  Concept Architect ⇄ Sense-Checker
    (three adversarial rounds — the concept is sent back twice before it passes)
    →  Deck Producer  →  the deck + cover art

Every logline, verdict, note and image prompt below is lifted from the real
run's journal and subagent transcripts — this is a curated cut, not a fiction.
The finished deck (``static/demo/the-casting/pitch-deck.html``) and its three
real cover images are surfaced by the Theatre as a finale reveal.

Run from the repo root:  python scripts/make_casting_demo.py
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSION = "ca5714a9-c057-4a11-9a5e-746865636173"
CWD = "/home/demo/pitch-factory"
MODEL = "claude-opus-4-8"
START = datetime(2026, 7, 3, 6, 49, 0, tzinfo=timezone.utc)

_lines: list[dict] = []
_last_uuid: dict[str, str | None] = {"main": None}


def _ts(seconds: float) -> str:
    return (START + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _base(t: float, chain: str) -> dict:
    uid = str(uuid.uuid4())
    rec = {
        "uuid": uid,
        "parentUuid": _last_uuid.get(chain),
        "sessionId": SESSION,
        "timestamp": _ts(t),
        "cwd": CWD,
        "version": "2.0.14",
        "isSidechain": chain != "main",
        "userType": "external",
    }
    _last_uuid[chain] = uid
    return rec


def user(t: float, content, chain: str = "main", tool_use_result=None) -> None:
    rec = _base(t, chain)
    rec["type"] = "user"
    rec["message"] = {"role": "user", "content": content}
    if tool_use_result is not None:
        rec["toolUseResult"] = tool_use_result
    _lines.append(rec)


def assistant(t: float, blocks: list[dict], chain: str = "main",
              ctx: int = 0, out: int = 0) -> None:
    rec = _base(t, chain)
    rec["type"] = "assistant"
    rec["requestId"] = f"req_{uuid.uuid4().hex[:12]}"
    rec["message"] = {
        "role": "assistant", "model": MODEL, "content": blocks,
        "usage": {
            "input_tokens": max(0, ctx - 1000), "output_tokens": out,
            "cache_read_input_tokens": min(1000, ctx),
            "cache_creation_input_tokens": 0,
        },
    }
    _lines.append(rec)


def tool_use(name: str, tool_input: dict) -> tuple[dict, str]:
    call_id = f"toolu_{uuid.uuid4().hex[:20]}"
    return {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}, call_id


def tool_result(t: float, call_id: str, content: str, chain: str = "main",
                tur=None, is_error: bool = False) -> None:
    block = {"type": "tool_result", "tool_use_id": call_id, "content": content}
    if is_error:
        block["is_error"] = True
    user(t, [block], chain=chain, tool_use_result=tur)


def web_result(text: str) -> dict:
    return {"type": "text", "text": text}


# ── The delegation spine ─────────────────────────────────────────────────────
# Each teammate is (chain, Task description, subagent_type, prompt). The prompt
# is reused verbatim as the sidechain's root user message so the adapter pairs
# them; the description becomes the sprite's name, the type its role subtitle.

P_SCOUT = (
    "You are the Trend Scout for a factual TV production company. Research what is "
    "genuinely hot right now — mid-2026 news cycles, cultural conversations, and the "
    "state of the unscripted commissioning market. Return a read on the landscape plus "
    "a ranked shortlist of format seeds, each with a why-now and an honest note on what "
    "is unverified."
)
P_ARCH_1 = (
    "You are the Concept Architect. Take the Trend Scout's top seed — the creator-to-"
    "reality casting pipeline — and turn it into a returnable unscripted format: title, "
    "logline, series type, format mechanics, cast and access, tone and comparables, "
    "target platform. Make the 'why this idea' argument."
)
P_SENSE_1 = (
    "You are the Sense-Checker. Pressure-test this format concept adversarially, before "
    "it goes anywhere near a pitch deck. Challenge originality, produceability, why-now "
    "and mechanic clarity. Return a verdict — APPROVE or REVISE — with actionable notes."
)
P_ARCH_2 = (
    "The Sense-Checker sent THE CASTING back. Revise it: name and differentiate the real "
    "competition comps, add an explicit episode-by-stage grid, and clarify the wired-"
    "house stage. Keep the hook narrow and honest."
)
P_SENSE_2 = (
    "Pressure-test the revised concept again, adversarially. Has it answered round one? "
    "What still blocks a greenlight?"
)
P_ARCH_3 = (
    "Revise once more against round two: widen the comps to the full 'real job as prize' "
    "field, state the funnel-scaling rule, and hold on to the honest caveats."
)
P_SENSE_3 = (
    "Final adversarial pass. Is this greenlight-readable from a one-pager, or not yet?"
)
P_DECK = (
    "You are the Deck Producer. Turn the approved THE CASTING concept into a tight "
    "3-page pitch deck — cover, the format, why-now/why-us — and write three cover-art "
    "image prompts set in one consistent visual world."
)

# Real image prompts (abbreviated from the run), one consistent world.
IMG1 = ("A single young creator sits alone in a stark, professional casting room, lit by "
        "the cold blue glow of a monitor showing their own dailies; three casting-panel "
        "judges in silhouette lean in behind a long table.")
IMG2 = ("Inside the wired casting house at night, five creators sit close on a low modular "
        "sofa mid-conversation, one small radio mic clipped to a collar in the foreground — "
        "the one bounded 24-hour hot-mic day.")
IMG3 = ("A wide, high-ceilinged studio soundstage at night, half boardroom and half live-"
        "finale set: a long panel table downstage with three silhouetted judges, a massive "
        "screen upstage flaring to life.")


def spawn(t: float, description: str, subagent_type: str, prompt: str,
          ctx: int, out: int) -> str:
    """Emit a Task tool_use on the main chain; return its call_id."""
    tk, tk_id = tool_use("Task", {"description": description,
                                  "prompt": prompt, "subagent_type": subagent_type})
    assistant(t, [tk], ctx=ctx, out=out)
    return tk_id


def main() -> None:
    # ── The commissioning brief ──────────────────────────────────────────────
    user(0,
         "Run as a factual-TV production company and develop a brand-new unscripted "
         "format from scratch. Scout what's genuinely hot right now, turn the strongest "
         "seed into a returnable format, pressure-test it hard before it goes near a "
         "buyer, then produce a 3-page pitch deck with cover art. Work as a team.")

    # ── Series Producer sets the slate up ────────────────────────────────────
    assistant(4, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text":
            "I'll run this like a real development slate. A Trend Scout first, to find "
            "what's actually hot in mid-2026. Then a Concept Architect turns the best "
            "seed into a format — but nothing goes to a deck until a Sense-Checker has "
            "tried to tear it apart. I'll loop those two until it survives, then hand to "
            "a Deck Producer for the pages and cover art."},
    ], ctx=9800, out=240)

    tw, tw_id = tool_use("TodoWrite", {"todos": [
        {"content": "Scout mid-2026 trends for a format seed", "status": "in_progress"},
        {"content": "Architect the seed into a returnable format", "status": "pending"},
        {"content": "Sense-check it adversarially until it survives", "status": "pending"},
        {"content": "Produce the 3-page deck + cover art", "status": "pending"},
    ]})
    assistant(7, [tw], ctx=10100, out=120)
    tool_result(7.4, tw_id, "Todos have been modified successfully")

    # ── Trend Scout ──────────────────────────────────────────────────────────
    t_scout = spawn(12, "Trend Scout", "Research", P_SCOUT, ctx=10600, out=120)

    _last_uuid["s1"] = None
    user(13, P_SCOUT, chain="s1")
    sw1, sw1_id = tool_use("WebSearch", {"query": "unscripted factual commissioning trends mid 2026 orders down"})
    assistant(16, [sw1], chain="s1", ctx=4200, out=90)
    tool_result(18, sw1_id,
                "Realscreen/ARTAS 'Industry Beats': unscripted series orders down ~31% "
                "year-over-year while original streaming consumption is up ~18% — buyers "
                "making 'fewer, bigger bets' and avoiding genre experiments.",
                chain="s1", tur=web_result("ok"))
    sw2, sw2_id = tool_use("WebSearch", {"query": "creators cast into reality TV TikTok Instagram deals 2026 Alix Earle Bravo"})
    assistant(22, [sw2], chain="s1", ctx=4900, out=90)
    tool_result(24, sw2_id,
                "Netflix signed influencer Alix Earle to a 2026 unscripted series; Peacock "
                "launching a Bravo-talent microdrama slate; talent agencies report ~30% "
                "year-on-year rise in cross-platform creator deals.",
                chain="s1", tur=web_result("ok"))
    assistant(30, [{"type": "text", "text":
        "Landscape: a 'fewer, bigger bets' contraction — orders down ~31% YoY. Six seeds "
        "ranked. The strongest under-served one is the creator-to-reality casting "
        "pipeline: everyone reports it from outside, nobody's made the show. Scale claims "
        "flagged as my synthesis, not a reported commissioning trend."}],
        chain="s1", ctx=6400, out=280)
    tool_result(33, t_scout,
                "Landscape: unscripted in a 'fewer, bigger bets' contraction (orders "
                "~-31% YoY). Six ranked seeds. Top under-served pick — 'Manufactured': the "
                "machine that turns creators into reality cast, a system no series has "
                "shown from the inside.",
                tur=web_result("ok"))

    assistant(37, [{"type": "text", "text":
        "Of the six, the creator-casting pipeline is the one nobody has made — everyone "
        "documents it from the outside. Let's build the format that IS the casting."}],
        ctx=12800, out=170)

    # ── Concept Architect — round 1 ──────────────────────────────────────────
    t_arch1 = spawn(41, "Concept Architect", "Creative", P_ARCH_1, ctx=13200, out=120)
    _last_uuid["s2"] = None
    user(42, P_ARCH_1, chain="s2")
    assistant(46, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text":
            "Flip it inside-out: don't document the casting machine — be it. THE CASTING: "
            "creators run the real audition gauntlet casting directors actually use — "
            "chemistry reads, a hot-mic house, network pitch tests — competing not for a "
            "trophy but for a genuine, contractually binding role on the network's next "
            "show."}],
        chain="s2", ctx=5200, out=260)
    tool_result(52, t_arch1,
                "THE CASTING — creators run the real casting gauntlet for an actual role "
                "on the network's next show. 8x60, returnable franchise: each season casts "
                "a different real show on the slate. Flips the 'Manufactured' documentary "
                "inside-out — the season itself produces a cast, on camera.",
                tur=web_result("ok"))

    # ── Sense-Checker — round 1 ──────────────────────────────────────────────
    t_sense1 = spawn(56, "Sense-Checker", "Critic", P_SENSE_1, ctx=14000, out=120)
    _last_uuid["s3"] = None
    user(57, P_SENSE_1, chain="s3")
    assistant(61, [{"type": "text", "text":
        "Verdict: REVISE. The 'flips documentaries inside-out' claim is weak — the closest "
        "comps aren't documentaries at all, they're competition formats with the identical "
        "prize mechanic (Food Network Star, VH1's Scream Queens). There's no episode-by-"
        "stage grid. And the hot-mic house — one bounded event, or continuous surveillance? "
        "The consent and rig implications are unspecified."}],
        chain="s3", ctx=5600, out=300)
    tool_result(66, t_sense1,
                "REVISE. Comps are competition formats (Food Network Star, Scream Queens), "
                "not documentaries — name them and differentiate. Add an explicit episode-"
                "by-stage grid. Clarify the hot-mic house: one bounded stage or continuous.",
                tur=web_result("ok"))

    assistant(70, [{"type": "text", "text":
        "Sent back — and the Sense-Checker is right. The comps are Food Network Star and "
        "Scream Queens, not documentaries. Back to the Architect to name them and grid "
        "the funnel."}], ctx=16200, out=170)

    # ── Concept Architect — round 2 ──────────────────────────────────────────
    t_arch2 = spawn(74, "Concept Architect", "Creative · rev 2", P_ARCH_2, ctx=16600, out=120)
    _last_uuid["s4"] = None
    user(75, P_ARCH_2, chain="s4")
    assistant(80, [{"type": "text", "text":
        "Revised. Added a Competitive Comps section — Food Network Star and Scream Queens "
        "named and differentiated. Explicit funnel grid: 20 → 14 → 11 → 9 → 7 → 6 → 5 "
        "across EP2-7, one stage per episode. The wired house is ONE bounded 24-hour hot-"
        "mic day; the rest of the season is a normal crewed multicam rig, not 24/7 "
        "surveillance."}],
        chain="s4", ctx=6100, out=280)
    tool_result(85, t_arch2,
                "v2: comps named and differentiated; explicit episode grid "
                "(20-14-11-9-7-6-5); wired house clarified as one bounded 24-hour stage. "
                "Hook restated narrowly.",
                tur=web_result("ok"))

    # ── Sense-Checker — round 2 ──────────────────────────────────────────────
    t_sense2 = spawn(89, "Sense-Checker", "Critic · rev 2", P_SENSE_2, ctx=17400, out=120)
    _last_uuid["s5"] = None
    user(90, P_SENSE_2, chain="s5")
    assistant(95, [{"type": "text", "text":
        "Still REVISE — but narrowing, and the document is unusually candid on cost and "
        "duty-of-care. Widen the comps to The Apprentice and Hell's Kitchen — both "
        "literally 'the prize is a real job'. Resolve the funnel-portability math for "
        "non-ensemble seasons. And get a discrimination-specific legal read on judging by "
        "casting 'type' before any real casting director is named."}],
        chain="s5", ctx=6600, out=300)
    tool_result(100, t_sense2,
                "REVISE (narrowing). Expand comps to Apprentice / Hell's Kitchen. Fix "
                "funnel-portability math across season types. Commission a discrimination "
                "read on 'type' casting before naming a real CD.",
                tur=web_result("ok"))

    assistant(104, [{"type": "text", "text":
        "Still a revise, but the notes are narrowing to specifics now, not fundamentals. "
        "One more pass."}], ctx=18800, out=150)

    # ── Concept Architect — round 3 ──────────────────────────────────────────
    t_arch3 = spawn(108, "Concept Architect", "Creative · rev 3", P_ARCH_3, ctx=19200, out=120)
    _last_uuid["s6"] = None
    user(109, P_ARCH_3, chain="s6")
    assistant(114, [{"type": "text", "text":
        "v3. Comps widened to the whole 'real job as prize' lane — The Apprentice, Hell's "
        "Kitchen, ANTM's actual prize (an agency contract, not a trophy) — alongside the "
        "Idol / X Factor 'real contract' DNA. The funnel now scales by a stated rule to "
        "the downstream show's actual cast-size need."}],
        chain="s6", ctx=7000, out=270)
    tool_result(119, t_arch3,
                "v3: comps widened to the full 'real job as prize' field; funnel scaling "
                "rule stated; honest caveats kept.",
                tur=web_result("ok"))

    # ── Sense-Checker — round 3 (capped) ─────────────────────────────────────
    t_sense3 = spawn(123, "Sense-Checker", "Critic · rev 3", P_SENSE_3, ctx=17800, out=120)
    _last_uuid["s7"] = None
    user(124, P_SENSE_3, chain="s7")
    assistant(130, [{"type": "text", "text":
        "Verdict: REVISE — but greenlight-readable as written for a single season. It's a "
        "crowded lane and I won't call it a fresh format grammar. The surviving notes are "
        "production-physics: Stage-1 chemistry-reads capacity at larger intakes, and a real "
        "cost model before repeating the 'Love Island budget' line. Those belong in the "
        "deck as honest caveats, not blockers."}],
        chain="s7", ctx=7400, out=300)
    tool_result(136, t_sense3,
                "REVISE, but greenlight-readable for S1. Remaining notes are production-"
                "physics (Stage-1 capacity, a real cost model) — honest caveats for the "
                "deck, not dealbreakers.",
                tur=web_result("ok"))

    assistant(140, [{"type": "text", "text":
        "Three rounds in, the Sense-Checker finally calls it greenlight-readable — the "
        "notes left standing are honest caveats, not dealbreakers. THE CASTING survived "
        "being pulled apart. To the Deck Producer."}], ctx=20400, out=210)

    # ── Deck Producer ────────────────────────────────────────────────────────
    t_deck = spawn(145, "Deck Producer", "Producer", P_DECK, ctx=20800, out=120)
    _last_uuid["s8"] = None
    user(146, P_DECK, chain="s8")
    assistant(152, [{"type": "text", "text":
        "Three pages. P1 THE CASTING — the audition process reality TV has never shown "
        "you. P2 THE FORMAT — 8x60, one funnel stage per episode, judged by a panel of "
        "working casting directors. P3 WHY NOW, WHY US — creators are already being cast; "
        "the process itself has never been on screen. Three cover-art prompts in one cold "
        "casting-studio palette — teal-grey and amber, with a single hot-magenta accent."}],
        chain="s8", ctx=7200, out=300)
    tool_result(158, t_deck,
                "3-page deck: THE CASTING / THE FORMAT / WHY NOW, WHY US. Three cover-art "
                "prompts in one consistent world (teal-grey + amber, a single magenta "
                "accent).",
                tur=web_result("ok"))

    # ── Series Producer assembles the deck + cover art ───────────────────────
    assistant(163, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text":
            "Deck spec approved. I'll generate the three cover images from the Deck "
            "Producer's prompts, then build the pages into a single self-contained deck."},
    ], ctx=21600, out=190)

    g1, g1_id = tool_use("mcp__claude_ai_Magnific__images_generate", {"prompt": IMG1})
    assistant(167, [g1], ctx=22000, out=90)
    tool_result(171, g1_id, "Generated cover art — 'the casting: the room' (1536x1024).",
                tur=web_result("ok"))
    g2, g2_id = tool_use("mcp__claude_ai_Magnific__images_generate", {"prompt": IMG2})
    assistant(173, [g2], ctx=22300, out=90)
    tool_result(177, g2_id, "Generated cover art — 'the wired house' (1536x1024).",
                tur=web_result("ok"))
    g3, g3_id = tool_use("mcp__claude_ai_Magnific__images_generate", {"prompt": IMG3})
    assistant(179, [g3], ctx=22600, out=90)
    tool_result(183, g3_id, "Generated cover art — 'the finale soundstage' (1536x1024).",
                tur=web_result("ok"))

    w, w_id = tool_use("Write", {"file_path": f"{CWD}/the-casting/pitch-deck.html",
                                 "content": "<!-- THE CASTING — 3-page pitch deck -->"})
    assistant(187, [w], ctx=23000, out=140)
    tool_result(187.6, w_id, "File created successfully.", tur=web_result("ok"))

    tw2, tw2_id = tool_use("TodoWrite", {"todos": [
        {"content": "Scout mid-2026 trends for a format seed", "status": "completed"},
        {"content": "Architect the seed into a returnable format", "status": "completed"},
        {"content": "Sense-check it adversarially until it survives", "status": "completed"},
        {"content": "Produce the 3-page deck + cover art", "status": "completed"},
    ]})
    assistant(191, [tw2], ctx=23400, out=120)
    tool_result(191.3, tw2_id, "Todos have been modified successfully")

    assistant(197, [{"type": "text", "text":
        "THE CASTING is deck-ready: TikTok and Instagram creators run the real casting "
        "gauntlet for actual jobs on the network's next show. The Trend Scout found the "
        "seed, the Concept Architect and Sense-Checker fought over it across three rounds, "
        "the Deck Producer shaped the pages, and I generated the cover art and built the "
        "deck — three pages, three images, one format that survived being pulled apart."}],
        ctx=24200, out=300)

    out_path = Path(__file__).resolve().parent.parent / "static" / "demo" / "the_casting_run.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in _lines:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {len(_lines)} lines to {out_path}")


if __name__ == "__main__":
    main()
