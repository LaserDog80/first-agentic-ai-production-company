"""Generate the bundled demo transcript for the Theatre.

Writes ``static/demo/demo_session.jsonl`` — a realistic Claude Code session
transcript (same line format as ``~/.claude/projects/*/*.jsonl``) telling a
small multi-agent story: Claude investigates flaky checkout tests, spawns
two subagents to research in parallel, applies a fix, and verifies it.

Run from the repo root:  python scripts/make_demo_transcript.py
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSION = "d3m0aaaa-1111-2222-3333-444455556666"
CWD = "/home/demo/shop-backend"
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
    user(0, "Our checkout tests have been flaky all week — sometimes "
            "test_payment_retry passes, sometimes it times out. Find the root "
            "cause and fix it.")

    # ── Claude reads the ground first ────────────────────────────────────
    assistant(4, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "I'll investigate the flaky checkout tests. First "
         "let me map out where the payment retry logic and its tests live, then "
         "I'll dig into the failure pattern."},
    ], ctx=9800, out=210)

    tw, tw_id = tool_use("TodoWrite", {"todos": [
        {"content": "Locate the flaky test and retry logic", "status": "in_progress"},
        {"content": "Find the root cause of the timeout", "status": "pending"},
        {"content": "Fix and verify with the test suite", "status": "pending"},
    ]})
    assistant(7, [tw], ctx=10100, out=90)
    tool_result(7.4, tw_id, "Todos have been modified successfully")

    g1, g1_id = tool_use("Grep", {"pattern": "test_payment_retry", "glob": "tests/**"})
    assistant(11, [g1], ctx=10400, out=70)
    tool_result(12, g1_id, "tests/checkout/test_payments.py",
                tur=bash_result("tests/checkout/test_payments.py"))

    r1, r1_id = tool_use("Read", {"file_path": f"{CWD}/tests/checkout/test_payments.py"})
    assistant(16, [r1], ctx=10800, out=60)
    tool_result(16.5, r1_id, "1\timport pytest\n2\tfrom checkout.payments import charge_with_retry\n…",
                tur={"type": "file", "file": {"filePath": "tests/checkout/test_payments.py", "numLines": 184}})

    # ── Delegation: two subagents in parallel ────────────────────────────
    assistant(24, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "The test wraps charge_with_retry with a 5s "
         "timeout. Two threads to pull on — the retry/backoff maths, and the "
         "mock payment gateway's latency config. I'll delegate both "
         "investigations so they run in parallel."},
    ], ctx=14200, out=180)

    p1 = ("Audit the retry/backoff implementation in checkout/payments.py. "
          "Work out the worst-case total wall-clock time of charge_with_retry "
          "with default settings, and report the numbers.")
    t1, t1_id = tool_use("Task", {"description": "Audit retry backoff timing",
                                  "prompt": p1, "subagent_type": "Explore"})
    p2 = ("Investigate the mock payment gateway used by the checkout tests "
          "(tests/checkout/conftest.py and fixtures). Find any injected latency, "
          "jitter, or randomness that could make timing nondeterministic.")
    t2, t2_id = tool_use("Task", {"description": "Trace mock gateway latency",
                                  "prompt": p2, "subagent_type": "Explore"})
    assistant(28, [t1, t2], ctx=14500, out=260)

    # ── Sidechain 1: retry auditor ───────────────────────────────────────
    _last_uuid["s1"] = None
    user(29, p1, chain="s1")
    s1r, s1r_id = tool_use("Read", {"file_path": f"{CWD}/checkout/payments.py"})
    assistant(33, [s1r], chain="s1", ctx=4200, out=60)
    tool_result(33.5, s1r_id, "1\tMAX_RETRIES = 4\n2\tBASE_DELAY = 0.4\n…", chain="s1",
                tur={"type": "file", "file": {"filePath": "checkout/payments.py", "numLines": 96}})
    s1b, s1b_id = tool_use("Bash", {
        "command": "python -c \"print(sum(0.4 * 2**i for i in range(4)))\"",
        "description": "Sum worst-case exponential backoff"})
    assistant(39, [s1b], chain="s1", ctx=5100, out=80)
    tool_result(40, s1b_id, "6.0", chain="s1", tur=bash_result("6.0"))
    assistant(46, [{"type": "text", "text":
        "Worst case: 4 retries with exponential backoff (0.4s base, factor 2) "
        "= 0.4+0.8+1.6+3.2 = 6.0s of sleep alone, before request time. The "
        "test's 5s timeout is mathematically beatable only when an early "
        "attempt succeeds — that's the flake."}], chain="s1", ctx=5600, out=140)

    # ── Sidechain 2: gateway tracer ──────────────────────────────────────
    _last_uuid["s2"] = None
    user(29.5, p2, chain="s2")
    s2g, s2g_id = tool_use("Grep", {"pattern": "sleep|latency|random", "path": "tests/checkout"})
    assistant(34, [s2g], chain="s2", ctx=4100, out=70)
    tool_result(35, s2g_id,
                "tests/checkout/conftest.py:41: time.sleep(random.uniform(0.1, 0.9))",
                chain="s2", tur=bash_result(
                    "tests/checkout/conftest.py:41: time.sleep(random.uniform(0.1, 0.9))"))
    s2r, s2r_id = tool_use("Read", {"file_path": f"{CWD}/tests/checkout/conftest.py"})
    assistant(41, [s2r], chain="s2", ctx=4900, out=60)
    tool_result(41.5, s2r_id, "1\t@pytest.fixture\n2\tdef mock_gateway():\n…", chain="s2",
                tur={"type": "file", "file": {"filePath": "tests/checkout/conftest.py", "numLines": 88}})
    assistant(52, [{"type": "text", "text":
        "The mock gateway injects random latency: time.sleep(random.uniform(0.1, "
        "0.9)) per call, unseeded. Combined with retries, total test time swings "
        "by several seconds run-to-run. That randomness is the nondeterminism."}],
        chain="s2", ctx=5400, out=130)

    # ── Reports land back with the orchestrator ──────────────────────────
    tool_result(47, t1_id,
                "Worst-case charge_with_retry wall-clock is 6.0s of backoff sleep "
                "alone (4 retries, base 0.4s, factor 2) — already over the test's "
                "5s timeout before any request time is counted.",
                tur={"type": "text"})
    tool_result(53, t2_id,
                "Mock gateway adds unseeded random latency of 0.1–0.9s per call "
                "(tests/checkout/conftest.py:41). With up to 5 calls per test, "
                "total runtime varies by ~4s between runs.",
                tur={"type": "text"})

    assistant(60, [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "Both reports agree: the 5s timeout can never "
         "safely contain worst-case backoff (6s) plus random gateway latency "
         "(up to 4.5s). The test only ever passed when early attempts succeeded. "
         "The right fix is to make backoff configurable and have the test inject "
         "a fast schedule, rather than raising the timeout and slowing CI."},
    ], ctx=21400, out=240)

    e1, e1_id = tool_use("Edit", {"file_path": f"{CWD}/checkout/payments.py",
                                  "old_string": "BASE_DELAY = 0.4",
                                  "new_string": "BASE_DELAY = 0.4  # overridable"})
    assistant(66, [e1], ctx=21900, out=150)
    tool_result(66.5, e1_id, "The file has been updated.", tur={"type": "text"})

    e2, e2_id = tool_use("Edit", {"file_path": f"{CWD}/tests/checkout/test_payments.py",
                                  "old_string": "charge_with_retry(order)",
                                  "new_string": "charge_with_retry(order, base_delay=0.01)"})
    assistant(70, [e2], ctx=22300, out=140)
    tool_result(70.4, e2_id, "The file has been updated.", tur={"type": "text"})

    b1, b1_id = tool_use("Bash", {"command": "pytest tests/checkout -q",
                                  "description": "Run the checkout test suite"})
    assistant(75, [b1], ctx=22800, out=80)
    tool_result(83, b1_id, "F..................\n1 failed, 18 passed",
                tur=bash_result("F..................\n1 failed, 18 passed"), is_error=True)

    assistant(90, [{"type": "text", "text": "One test still fails — it asserts on "
        "the old default delay. The seed fixture also needs pinning so the mock "
        "gateway is deterministic."}], ctx=24100, out=120)

    e3, e3_id = tool_use("Edit", {"file_path": f"{CWD}/tests/checkout/conftest.py",
                                  "old_string": "time.sleep(random.uniform(0.1, 0.9))",
                                  "new_string": "time.sleep(0.01)"})
    assistant(94, [e3], ctx=24600, out=130)
    tool_result(94.5, e3_id, "The file has been updated.", tur={"type": "text"})

    b2, b2_id = tool_use("Bash", {"command": "pytest tests/checkout -q",
                                  "description": "Re-run the checkout test suite"})
    assistant(98, [b2], ctx=25000, out=70)
    tool_result(107, b2_id, "...................\n19 passed in 3.41s",
                tur=bash_result("...................\n19 passed in 3.41s"))

    tw2, tw2_id = tool_use("TodoWrite", {"todos": [
        {"content": "Locate the flaky test and retry logic", "status": "completed"},
        {"content": "Find the root cause of the timeout", "status": "completed"},
        {"content": "Fix and verify with the test suite", "status": "completed"},
    ]})
    assistant(110, [tw2], ctx=25400, out=90)
    tool_result(110.3, tw2_id, "Todos have been modified successfully")

    assistant(116, [{"type": "text", "text":
        "Fixed. Root cause was two compounding timing problems: worst-case "
        "retry backoff (6.0s) already exceeded the test's 5s timeout, and the "
        "mock gateway injected unseeded random latency of up to 0.9s per call. "
        "The tests now inject a fast backoff schedule and a deterministic "
        "gateway delay — 19/19 passing in 3.4s."}], ctx=26200, out=220)

    out_path = Path(__file__).resolve().parent.parent / "static" / "demo" / "demo_session.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in _lines:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {len(_lines)} lines to {out_path}")


if __name__ == "__main__":
    main()
