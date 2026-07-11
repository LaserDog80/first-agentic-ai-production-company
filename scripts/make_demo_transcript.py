"""Generate the bundled demo transcript for the Theatre.

Writes ``static/demo/demo_session.jsonl`` — a realistic Claude Code session
transcript (same line format as ``~/.claude/projects/*/*.jsonl``) telling the
production-company story from the original pitch-deck pipeline: a one-line
commissioning brief comes in, Claude sets the editorial vision, hires a
Researcher, a Director and a Production Manager in parallel, then a Producer
to assemble the deck — and ships a broadcastable pitch.

Run from the repo root:  python scripts/make_demo_transcript.py
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSION = "d3m0aaaa-1111-2222-3333-444455556666"
CWD = "/home/demo/pitch-factory"
MODEL = "claude-fable-5"
START = datetime(2026, 7, 8, 14, 3, 12, tzinfo=timezone.utc)

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


def bash_result(stdout: str) -> dict:
    return {"stdout": stdout, "stderr": "", "interrupted": False, "isImage": False}


def main() -> None:
    # ── The brief ────────────────────────────────────────────────────────
    user(0, "The commissioning round closes Friday. Pitch me 'The Last "
            "Lighthouse Keepers' — a 3-part factual series about the final "
            "generation of UK lighthouse keepers. I need a broadcastable pitch "
            "deck: editorial vision, key facts and access, a visual treatment, "
            "and a realistic budget.")

    # ── Claude puts on the series-producer hat ───────────────────────────
    assistant(4, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "I'll run this like a commissioning pitch. "
         "First the editorial vision, then I'll hire a crew in parallel — "
         "research, treatment and budget — and assemble the deck from their "
         "reports."},
    ], ctx=9800, out=210)

    tw, tw_id = tool_use("TodoWrite", {"todos": [
        {"content": "Set the editorial vision", "status": "in_progress"},
        {"content": "Research facts, archive and access", "status": "pending"},
        {"content": "Define the visual treatment", "status": "pending"},
        {"content": "Cost a 3-part shoot", "status": "pending"},
        {"content": "Assemble the pitch deck", "status": "pending"},
    ]})
    assistant(7, [tw], ctx=10100, out=110)
    tool_result(7.4, tw_id, "Todos have been modified successfully")

    r1, r1_id = tool_use("Read", {"file_path": f"{CWD}/briefs/lighthouse_keepers.md"})
    assistant(11, [r1], ctx=10400, out=60)
    tool_result(11.5, r1_id, "1\t# The Last Lighthouse Keepers — one-line brief\n2\t…",
                tur={"type": "file", "file": {"filePath": "briefs/lighthouse_keepers.md", "numLines": 42}})

    g1, g1_id = tool_use("Grep", {"pattern": "lighthouse|coastal", "path": "archive/"})
    assistant(16, [g1], ctx=10900, out=70)
    tool_result(17, g1_id, "archive/2019_coastal_lives.md",
                tur=bash_result("archive/2019_coastal_lives.md"))

    # ── Delegation: three crew hires in parallel ─────────────────────────
    assistant(24, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "Vision: obsolescence and devotion — the last "
         "people who kept the lights while the world automated around them. "
         "We pitched coastal before (2019) but never got access; that's the "
         "gap to close. I'll hire the crew in parallel: a researcher on facts "
         "and access, a director on the visual treatment, a production "
         "manager on the budget."},
    ], ctx=14200, out=230)

    p1 = ("Research 'The Last Lighthouse Keepers': how many manned lighthouses "
          "remain in the UK, when automation completed, which former keepers "
          "are alive and interviewable, and what archive footage exists. "
          "Confirm who controls access to the towers.")
    t1, t1_id = tool_use("Task", {"description": "Researcher",
                                  "prompt": p1, "subagent_type": "Fact Finder"})
    p2 = ("Define the visual treatment for a 3-part factual series 'The Last "
          "Lighthouse Keepers': episode arc, visual grammar, tone references. "
          "Check archive/2019_coastal_lives.md for what we pitched before and "
          "deliberately depart from it.")
    t2, t2_id = tool_use("Task", {"description": "Director",
                                  "prompt": p2, "subagent_type": "Creative Visionary"})
    p3 = ("Cost a 3x60-minute factual series shot at three remote UK "
          "lighthouse locations: core crew day rates, 18 shoot days, kit, "
          "travel and access boats, archive licensing. Give a realistic range.")
    t3, t3_id = tool_use("Task", {"description": "Production Manager",
                                  "prompt": p3, "subagent_type": "Logistics & Budget"})
    assistant(28, [t1, t2, t3], ctx=14600, out=320)

    # ── Sidechain 1: the researcher ──────────────────────────────────────
    _last_uuid["s1"] = None
    user(29, p1, chain="s1")
    s1w, s1w_id = tool_use("WebSearch", {"query": "how many manned lighthouses remain UK Trinity House"})
    assistant(33, [s1w], chain="s1", ctx=4200, out=70)
    tool_result(35, s1w_id,
                "UK lighthouse automation completed 26 November 1998 (North "
                "Foreland, Kent). All 200+ Trinity House lighthouses now "
                "automated and monitored from Harwich.",
                chain="s1", tur={"type": "text"})
    s1f, s1f_id = tool_use("WebFetch", {"url": "https://www.trinityhouse.co.uk/lighthouses/access",
                                        "prompt": "Who controls filming access to the towers?"})
    assistant(40, [s1f], chain="s1", ctx=4900, out=80)
    tool_result(41.5, s1f_id, "403 Forbidden — the site refused the request.",
                chain="s1", is_error=True)
    assistant(46, [{"type": "text", "text":
        "Direct fetch blocked — pivoting to press coverage and the keepers' "
        "association instead."}], chain="s1", ctx=5300, out=90)
    s1w2, s1w2_id = tool_use("WebSearch", {"query": "last UK lighthouse keepers interviews Association of Lighthouse Keepers"})
    assistant(50, [s1w2], chain="s1", ctx=5600, out=70)
    tool_result(52, s1w2_id,
                "Association of Lighthouse Keepers maintains a register of "
                "former keepers; several gave 25th-anniversary interviews in "
                "2023. BBC Archive and BFI hold automation-era footage.",
                chain="s1", tur={"type": "text"})
    assistant(58, [{"type": "text", "text":
        "Automation completed 26 Nov 1998 at North Foreland — the anniversary "
        "is our news hook. Former keepers are alive, organised and on the "
        "record via the Association of Lighthouse Keepers. Archive exists at "
        "BBC and BFI. Access to towers runs through Trinity House press "
        "office — a relationship to build, not a blocker."}],
        chain="s1", ctx=6200, out=160)

    # ── Sidechain 2: the director ────────────────────────────────────────
    _last_uuid["s2"] = None
    user(29.5, p2, chain="s2")
    s2r, s2r_id = tool_use("Read", {"file_path": f"{CWD}/archive/2019_coastal_lives.md"})
    assistant(34, [s2r], chain="s2", ctx=4100, out=60)
    tool_result(35.5, s2r_id, "1\t# Coastal Lives (2019 pitch, not commissioned)\n2\t…",
                chain="s2", tur={"type": "file", "file": {"filePath": "archive/2019_coastal_lives.md", "numLines": 120}})
    assistant(48, [{"type": "text", "text":
        "Treatment: one keeper per episode, one tower each — intimacy over "
        "geography. Slow cinema pacing, locked-off frames like the lamp "
        "itself, night interiors lit only by the rotating beam. The 2019 "
        "pitch was drone-heavy postcard coastline; we go the other way — "
        "inside the tower, faces and hands. Ep1 the last shift, Ep2 the "
        "automation, Ep3 what remains."}], chain="s2", ctx=5200, out=180)

    # ── Sidechain 3: the production manager ──────────────────────────────
    _last_uuid["s3"] = None
    user(30, p3, chain="s3")
    s3b, s3b_id = tool_use("Bash", {
        "command": "python -c \"print((450+400+350+250)*18)\"",
        "description": "Total core crew day rates x 18 shoot days"})
    assistant(36, [s3b], chain="s3", ctx=4300, out=80)
    tool_result(38, s3b_id, "26100", chain="s3", tur=bash_result("26100"))
    s3b2, s3b2_id = tool_use("Bash", {
        "command": "python -c \"print(26100+38000+21000+14500)\"",
        "description": "Crew + kit + travel/boats + archive licensing"})
    assistant(44, [s3b2], chain="s3", ctx=4800, out=80)
    tool_result(46, s3b2_id, "99600", chain="s3", tur=bash_result("99600"))
    assistant(55, [{"type": "text", "text":
        "Core crew (director/camera, sound, AP, runner) at standard day rates "
        "x 18 days = £26.1k. Kit £38k, remote travel and access boats £21k, "
        "archive licensing £14.5k. With post, insurance and 12% contingency: "
        "£310k–£380k for 3x60'. The boats are the swing item — weather days "
        "at sea rock the schedule."}], chain="s3", ctx=5500, out=170)

    # ── Reports land back with the orchestrator ──────────────────────────
    tool_result(50, t2_id,
                "Treatment: one keeper, one tower per episode — slow cinema, "
                "locked-off frames, night interiors lit by the rotating beam. "
                "Deliberately departs from the 2019 drone-postcard approach. "
                "Ep1 the last shift, Ep2 the automation, Ep3 what remains.",
                tur={"type": "text"})
    tool_result(57, t3_id,
                "Realistic range £310k–£380k for 3x60': crew £26.1k (18 days), "
                "kit £38k, travel/boats £21k, archive £14.5k, plus post and "
                "12% contingency. Boats/weather are the main schedule risk.",
                tur={"type": "text"})
    tool_result(60, t1_id,
                "Automation completed 26 Nov 1998 (North Foreland) — "
                "anniversary is the news hook. Former keepers organised and "
                "interviewable via the Association of Lighthouse Keepers; "
                "archive at BBC/BFI; tower access via Trinity House press "
                "office.",
                tur={"type": "text"})

    assistant(66, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "All three reports agree this is pitchable: "
         "a hard news hook (the automation anniversary), living access to "
         "the last keepers, a distinctive visual grammar, and a credible "
         "budget. One more hire — a producer to assemble the deck in house "
         "style and fact-check the claims."},
    ], ctx=21800, out=220)

    # ── Second wave: the producer assembles ──────────────────────────────
    p4 = ("Assemble the pitch deck for 'The Last Lighthouse Keepers' from the "
          "research, treatment and budget reports. House style: six slides — "
          "logline, why now, the keepers, the look, access & archive, budget. "
          "Flag any claim that lacks a source.")
    t4, t4_id = tool_use("Task", {"description": "Producer",
                                  "prompt": p4, "subagent_type": "Creative Coordinator"})
    assistant(70, [t4], ctx=22200, out=140)

    _last_uuid["s4"] = None
    user(71, p4, chain="s4")
    s4r, s4r_id = tool_use("Read", {"file_path": f"{CWD}/templates/house_style.md"})
    assistant(75, [s4r], chain="s4", ctx=3900, out=60)
    tool_result(76, s4r_id, "1\t# Deck house style — six slides, one idea per slide\n2\t…",
                chain="s4", tur={"type": "file", "file": {"filePath": "templates/house_style.md", "numLines": 31}})
    assistant(84, [{"type": "text", "text":
        "Deck assembled to house style — six slides, one idea per slide. "
        "Logline leads with the anniversary hook. One claim flagged and cut: "
        "'most visited heritage sites in the UK' had no source. Budget slide "
        "shows the range with the boats risk called out honestly."}],
        chain="s4", ctx=4800, out=150)

    tool_result(86, t4_id,
                "Six-slide deck assembled in house style. Cut one unsourced "
                "claim (visitor numbers). Logline: 'For 500 years someone "
                "kept the light. In 1998 we switched them off.'",
                tur={"type": "text"})

    # ── The deck ships ───────────────────────────────────────────────────
    w1, w1_id = tool_use("Write", {"file_path": f"{CWD}/decks/last_lighthouse_keepers.md",
                                   "content": "# The Last Lighthouse Keepers — pitch deck\n…"})
    assistant(92, [w1], ctx=23400, out=180)
    tool_result(92.6, w1_id, "File created successfully.", tur={"type": "text"})

    tw2, tw2_id = tool_use("TodoWrite", {"todos": [
        {"content": "Set the editorial vision", "status": "completed"},
        {"content": "Research facts, archive and access", "status": "completed"},
        {"content": "Define the visual treatment", "status": "completed"},
        {"content": "Cost a 3-part shoot", "status": "completed"},
        {"content": "Assemble the pitch deck", "status": "completed"},
    ]})
    assistant(103, [tw2], ctx=23800, out=110)
    tool_result(103.3, tw2_id, "Todos have been modified successfully")

    assistant(112, [{"type": "text", "text":
        "Pitch deck ready: decks/last_lighthouse_keepers.md. Six slides — "
        "logline built on the 26 Nov 1998 automation anniversary, living "
        "keepers on the record, a slow-cinema treatment that departs from "
        "our 2019 miss, and an honest £310k–£380k budget. Researcher, "
        "director and production manager worked in parallel; the producer "
        "assembled and fact-checked the deck."}], ctx=24600, out=240)

    out_path = Path(__file__).resolve().parent.parent / "static" / "demo" / "demo_session.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in _lines:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {len(_lines)} lines to {out_path}")


if __name__ == "__main__":
    main()
