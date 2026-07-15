"""Generate the 'THE CASTING' demo transcript for the Theatre.

Writes ``static/demo/the_casting_run.jsonl`` — a stage-ready cut of a *real*
agentic run (3 July 2026) that developed an unscripted TV format end to end.

The original run used the Workflow orchestrator, so its team lived in separate
``subagents/workflows/*`` files the theatre adapter never folds in — on stage it
looked like one lonely agent making a single opaque ``Workflow`` call. This cut
re-expresses that same run in the shape the adapter *does* render: each teammate
is a ``Task`` spawn with a matching ``isSidechain`` chain, so the cast assembles
itself on stage:

    Head of Development  →  Researcher
                         →  Producer  ⇄  Exec Producer   (they go back and forth,
                             one sprite each, across three rounds of notes)
                         →  Deck Producer  →  the deck + cover art

DEMO-ONLY SIMPLIFICATION: in reality the Producer/Exec-Producer loop re-hired a
fresh Workflow subagent each round. For a lay audience that reads as "why does a
new person keep walking on?" — so here each of those two roles is hired *once*
and their three rounds are interleaved before they report back. The spotlight
just returns to the same person, which is easier to follow. Everything they say
is still lifted from the real run's journal and subagent transcripts.

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


def say(t: float, text: str, chain: str, ctx: int, out: int) -> None:
    assistant(t, [{"type": "text", "text": text}], chain=chain, ctx=ctx, out=out)


def spawn(t: float, description: str, subagent_type: str, prompt: str,
          ctx: int, out: int) -> str:
    """Emit a Task tool_use on the main chain; return its call_id."""
    tk, tk_id = tool_use("Task", {"description": description,
                                  "prompt": prompt, "subagent_type": subagent_type})
    assistant(t, [tk], ctx=ctx, out=out)
    return tk_id


# ── The delegation spine ─────────────────────────────────────────────────────
# Each teammate's Task prompt is reused verbatim as its sidechain's root user
# message so the adapter pairs them; the description becomes the sprite's name,
# the subagent_type its role subtitle.

P_RESEARCH = (
    "You are the Researcher for a factual-TV production company. Research what is "
    "genuinely hot right now — mid-2026 news cycles, cultural conversations, and the "
    "state of the unscripted commissioning market. Return a read on the landscape plus "
    "a ranked shortlist of format seeds, each with a why-now and an honest note on what "
    "is unverified."
)
P_PRODUCE = (
    "You are the Producer. Take the Researcher's top seed — the creator-to-reality "
    "casting pipeline — and develop it into a returnable unscripted format: title, "
    "logline, series type, format mechanics, cast and access, tone and comparables, "
    "target platform. Then rework it against the Exec Producer's notes until it holds."
)
P_EXEC = (
    "You are the Exec Producer. Pressure-test the Producer's format adversarially, round "
    "by round, before it goes anywhere near a pitch deck. Challenge originality, "
    "produceability, why-now and mechanic clarity. Send it back with notes until it is "
    "greenlight-readable."
)
P_DECK = (
    "You are the Deck Producer. Turn the greenlit THE CASTING concept into a tight "
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


def main() -> None:
    # ── The commissioning brief ──────────────────────────────────────────────
    user(0,
         "Run as a factual-TV production company and develop a brand-new unscripted "
         "format from scratch. Research what's genuinely hot right now, turn the strongest "
         "seed into a returnable format, pressure-test it hard before it goes near a "
         "buyer, then produce a 3-page pitch deck with cover art. Work as a team.")

    # ── Head of Development sets the slate up ────────────────────────────────
    assistant(4, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text":
            "I'll run this like a real development slate. A Researcher first, to find "
            "what's genuinely hot in mid-2026. Then a Producer develops the strongest "
            "seed into a format while an Exec Producer pressure-tests it — round after "
            "round, until it survives. Then a Deck Producer builds the pages and cover "
            "art."},
    ], ctx=9800, out=240)

    tw, tw_id = tool_use("TodoWrite", {"todos": [
        {"content": "Research mid-2026 trends for a format seed", "status": "in_progress"},
        {"content": "Develop the seed into a returnable format", "status": "pending"},
        {"content": "Pressure-test it until it's greenlight-readable", "status": "pending"},
        {"content": "Produce the 3-page deck + cover art", "status": "pending"},
    ]})
    assistant(7, [tw], ctx=10100, out=120)
    tool_result(7.4, tw_id, "Todos have been modified successfully")

    # ── Researcher ───────────────────────────────────────────────────────────
    t_research = spawn(12, "Researcher", "research", P_RESEARCH, ctx=10600, out=120)

    _last_uuid["s1"] = None
    user(13, P_RESEARCH, chain="s1")
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
    say(30,
        "Landscape: a 'fewer, bigger bets' contraction — orders down ~31% YoY. Six seeds "
        "ranked. The strongest under-served one is the creator-to-reality casting "
        "pipeline: everyone reports it from outside, nobody's made the show. Scale claims "
        "flagged as my synthesis, not a reported commissioning trend.",
        chain="s1", ctx=6400, out=280)
    tool_result(33, t_research,
                "Landscape: unscripted in a 'fewer, bigger bets' contraction (orders "
                "~-31% YoY). Six ranked seeds. Top under-served pick — 'Manufactured': the "
                "machine that turns creators into reality cast, a system no series has "
                "shown from the inside.",
                tur=web_result("ok"))

    assistant(37, [{"type": "text", "text":
        "Of the six, the creator-casting pipeline is the one nobody has made — everyone "
        "documents it from outside. I'll put a Producer on developing it and an Exec "
        "Producer on tearing it apart — back and forth until it holds."}],
        ctx=12800, out=190)

    # ── Producer ⇄ Exec Producer: hired once each, three interleaved rounds ───
    # Both stay on stage through the debate; the spotlight moves between the two
    # fixed sprites instead of a new person arriving each round.
    t_prod = spawn(41, "Producer", "development", P_PRODUCE, ctx=13200, out=120)
    _last_uuid["s2"] = None
    user(42, P_PRODUCE, chain="s2")

    t_exec = spawn(45, "Exec Producer", "greenlight", P_EXEC, ctx=13600, out=120)
    _last_uuid["s3"] = None
    user(46, P_EXEC, chain="s3")

    # round 1
    say(50,
        "Flip it inside-out: don't document the casting machine — be it. THE CASTING: "
        "creators run the real audition gauntlet casting directors actually use — "
        "chemistry reads, a hot-mic house, network pitch tests — competing not for a "
        "trophy but for a genuine, contractually binding role on the network's next show.",
        chain="s2", ctx=5200, out=280)
    say(58,
        "REVISE. The 'flips documentaries inside-out' claim is weak — the closest comps "
        "aren't documentaries, they're competition formats with the identical prize "
        "mechanic (Food Network Star, Scream Queens). There's no episode-by-stage grid, "
        "and the hot-mic house — one bounded event, or continuous surveillance? — is "
        "unspecified.",
        chain="s3", ctx=5600, out=300)
    # round 2
    say(68,
        "Reworked. Named the real comps — Food Network Star, Scream Queens — and "
        "differentiated them. Added an explicit funnel grid: 20 → 14 → 11 → 9 → 7 → 6 → 5 "
        "across EP2-7. The wired house is one bounded 24-hour hot-mic day; the rest of "
        "the season is a normal crewed multicam rig, not 24/7 surveillance.",
        chain="s2", ctx=6100, out=280)
    say(78,
        "Better, and candid on cost and duty-of-care. Still REVISE: widen the comps to "
        "The Apprentice and Hell's Kitchen — both literally 'the prize is a real job'. "
        "Fix the funnel-portability math for other season types, and get a discrimination "
        "read on judging by casting 'type' before any real casting director is named.",
        chain="s3", ctx=6600, out=300)
    # round 3
    say(90,
        "v3. Comps widened to the whole 'real job as prize' lane — Apprentice, Hell's "
        "Kitchen, ANTM's actual prize (an agency contract, not a trophy) — alongside the "
        "Idol / X Factor 'real contract' DNA. The funnel now scales by a stated rule to "
        "the downstream show's actual cast-size need.",
        chain="s2", ctx=7000, out=270)
    say(100,
        "Now it's greenlight-readable for a single season. I still won't call it a fresh "
        "format grammar — it's a crowded lane — but the surviving notes are production-"
        "physics: Stage-1 capacity at larger intakes, and a real cost model. Those are "
        "honest caveats for the deck, not blockers. Cleared.",
        chain="s3", ctx=7400, out=300)

    tool_result(110, t_prod,
                "THE CASTING — creators run the real casting gauntlet for an actual role "
                "on the network's next show. 8x60, returnable franchise. Survived three "
                "rounds of the Exec Producer's notes: comps named and differentiated, "
                "funnel gridded, caveats kept honest.",
                tur=web_result("ok"))
    tool_result(113, t_exec,
                "Cleared to deck. Greenlight-readable for S1 — the remaining notes "
                "(Stage-1 capacity, a real cost model) are honest caveats to carry in the "
                "deck, not dealbreakers.",
                tur=web_result("ok"))

    assistant(117, [{"type": "text", "text":
        "Three rounds in, the Exec Producer clears it — the notes left standing are "
        "honest caveats, not dealbreakers. THE CASTING survived being pulled apart. Deck "
        "Producer, build the pages."}], ctx=20400, out=210)

    # ── Deck Producer ────────────────────────────────────────────────────────
    t_deck = spawn(121, "Deck Producer", "deck", P_DECK, ctx=20800, out=120)
    _last_uuid["s4"] = None
    user(122, P_DECK, chain="s4")
    say(128,
        "Three pages. P1 THE CASTING — the audition process reality TV has never shown "
        "you. P2 THE FORMAT — 8x60, one funnel stage per episode, judged by a panel of "
        "working casting directors. P3 WHY NOW, WHY US — creators are already being cast; "
        "the process itself has never been on screen. Three cover-art prompts in one cold "
        "casting-studio palette — teal-grey and amber, with a single hot-magenta accent.",
        chain="s4", ctx=7200, out=300)
    tool_result(134, t_deck,
                "3-page deck: THE CASTING / THE FORMAT / WHY NOW, WHY US. Three cover-art "
                "prompts in one consistent world (teal-grey + amber, a single magenta "
                "accent).",
                tur=web_result("ok"))

    # ── Head of Development assembles the deck + cover art ────────────────────
    assistant(139, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text":
            "Deck spec approved. I'll generate the three cover images from the Deck "
            "Producer's prompts, then build the pages into a single self-contained deck."},
    ], ctx=21600, out=190)

    g1, g1_id = tool_use("mcp__claude_ai_Magnific__images_generate", {"prompt": IMG1})
    assistant(143, [g1], ctx=22000, out=90)
    tool_result(147, g1_id, "Generated cover art — 'the casting: the room' (1536x1024).",
                tur=web_result("ok"))
    g2, g2_id = tool_use("mcp__claude_ai_Magnific__images_generate", {"prompt": IMG2})
    assistant(149, [g2], ctx=22300, out=90)
    tool_result(153, g2_id, "Generated cover art — 'the wired house' (1536x1024).",
                tur=web_result("ok"))
    g3, g3_id = tool_use("mcp__claude_ai_Magnific__images_generate", {"prompt": IMG3})
    assistant(155, [g3], ctx=22600, out=90)
    tool_result(159, g3_id, "Generated cover art — 'the finale soundstage' (1536x1024).",
                tur=web_result("ok"))

    w, w_id = tool_use("Write", {"file_path": f"{CWD}/the-casting/pitch-deck.html",
                                 "content": "<!-- THE CASTING — 3-page pitch deck -->"})
    assistant(163, [w], ctx=23000, out=140)
    tool_result(163.6, w_id, "File created successfully.", tur=web_result("ok"))

    tw2, tw2_id = tool_use("TodoWrite", {"todos": [
        {"content": "Research mid-2026 trends for a format seed", "status": "completed"},
        {"content": "Develop the seed into a returnable format", "status": "completed"},
        {"content": "Pressure-test it until it's greenlight-readable", "status": "completed"},
        {"content": "Produce the 3-page deck + cover art", "status": "completed"},
    ]})
    assistant(167, [tw2], ctx=23400, out=120)
    tool_result(167.3, tw2_id, "Todos have been modified successfully")

    assistant(173, [{"type": "text", "text":
        "THE CASTING is deck-ready: TikTok and Instagram creators run the real casting "
        "gauntlet for actual jobs on the network's next show. The Researcher found the "
        "seed, the Producer and Exec Producer fought it into shape across three rounds, "
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
