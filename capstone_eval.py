#!/usr/bin/env python3
"""
Run the capstone criteria (criteria.md, C1-C5) against the running server.

    .venv/bin/python capstone_eval.py --label before
    .venv/bin/python capstone_eval.py --label after --trials 3

For every trial and every scenario this starts `serve.py` as its own process
with that scenario's environment (AI201_FAULT, AI201_CACHE=0, its own log
file), waits for /health, sends the requests over HTTP, then stops it. So the
test goes through the same run path RUNNING.md documents, not a function call.

Scoring reads two things and compares them: what the client received (status,
JSON body, wall time) and what the server logged. Writes:

    results/capstone_<stamp>_<label>.md              the run log table + evidence
    results/capstone_<stamp>_<label>_t<N>.jsonl      the server's log, per trial
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
PORT = int(os.getenv("CAPSTONE_PORT", "5061"))
BASE = f"http://127.0.0.1:{PORT}"

MATCHING = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "platform sneakers size 8",
    "vintage jeans under $35",
    "denim jacket under $50",
]

# (name, body bytes or None, content type or None)
MALFORMED = [
    ("no body", None, None),
    ("not JSON", b"not json at all", "application/json"),
    ("empty query", b'{"query": ""}', "application/json"),
    ("whitespace query", b'{"query": "   "}', "application/json"),
    ("query is a number", b'{"query": 42}', "application/json"),
    ("body is a JSON array", b'["vintage tee"]', "application/json"),
]

TITLES = {
    "C1": "C1. A single 503 is retried and never seen",
    "C2": "C2. Outage: ≤10s, search kept, key not blamed",
    "C3": "C3. Rejected key: ≤2s, 1 attempt, no retry",
    "C4": "C4. Every request leaves one log line",
    "C5": "C5. Malformed input gets a 400, never a 500",
}
TARGETS = {"C1": "5 of 5", "C2": "5 of 5", "C3": "5 of 5", "C4": "21 of 21", "C5": "6 of 6"}


# ── driving the server ───────────────────────────────────────────────────────

def start_server(env_extra: dict, log_path: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env.pop("AI201_FAULT", None)
    env.update({"PORT": str(PORT), "AI201_CACHE": "0", "AI201_LOG": str(log_path)})
    env.update(env_extra)
    proc = subprocess.Popen(
        [sys.executable, "serve.py"], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=1).read()
            return proc
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit(f"serve.py didn't come up on port {PORT}")


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def post(body: bytes | None, ctype: str | None) -> dict:
    req = urllib.request.Request(f"{BASE}/ask", data=body if body is not None else b"",
                                 method="POST")
    if ctype:
        req.add_header("Content-Type", ctype)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    ms = round((time.perf_counter() - t0) * 1000)
    try:
        payload = json.loads(raw)
    except Exception:
        payload = None
    return {"status": status, "json": payload, "raw": raw[:300].decode("utf-8", "replace"),
            "client_ms": ms}


def ask(query: str) -> dict:
    return post(json.dumps({"query": query}).encode(), "application/json")


# ── one trial ────────────────────────────────────────────────────────────────

SCENARIOS = [
    ("C1", {"AI201_FAULT": "503x1"}),
    ("C2", {"AI201_FAULT": "503"}),
    ("C3", {"AI201_FAULT": "401"}),
    ("C5", {}),
]


def run_trial(stamp: str, label: str, n: int) -> dict:
    log_path = RESULTS / f"capstone_{stamp}_{label}_t{n}.jsonl"
    log_path.unlink(missing_ok=True)
    sent = []          # every request, in order: (scenario, name, client result)
    for crit, env in SCENARIOS:
        proc = start_server(env, log_path)
        try:
            if crit == "C5":
                for name, body, ctype in MALFORMED:
                    sent.append((crit, name, post(body, ctype)))
            else:
                for q in MATCHING:
                    sent.append((crit, q, ask(q)))
        finally:
            stop_server(proc)
        print(f"  trial {n} {crit}: {[r['status'] for c, _, r in sent if c == crit]}",
              flush=True)

    lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    return {"sent": sent, "lines": lines, "log_path": log_path}


# ── scoring, one function per criterion, matching criteria.md's wording ──────

def _parsed_lines(lines):
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            out.append(None)
    return out


def score(trial: dict) -> dict:
    sent, logs = trial["sent"], _parsed_lines(trial["lines"])
    aligned = len(logs) == len(sent)
    rows = {}

    def log_for(i):
        return logs[i] if aligned else None

    # C1
    ok, why = 0, []
    for i, (c, q, r) in enumerate(sent):
        if c != "C1":
            continue
        s = (r["json"] or {}) if isinstance(r["json"], dict) else {}
        lg = log_for(i) or {}
        passed = (r["status"] == 200 and s.get("error") is None and bool(s.get("fit_card"))
                  and lg.get("retries") == 2)
        ok += passed
        if not passed:
            why.append(f"{q}: status {r['status']}, error={str(s.get('error'))[:80]!r}, "
                       f"retries={lg.get('retries')}")
    rows["C1"] = (ok, 5, why)

    # C2
    ok, why = 0, []
    for i, (c, q, r) in enumerate(sent):
        if c != "C2":
            continue
        s = (r["json"] or {}) if isinstance(r["json"], dict) else {}
        lg = log_for(i) or {}
        err = s.get("error") or ""
        checks = {
            "≤10000ms": (lg.get("duration_ms") or 10**9) <= 10000,
            "search kept": s.get("selected_item") is not None,
            "says wait": "wait" in err.lower(),
            "no key blame": "GEMINI_API_KEY" not in err,
            "outcome": lg.get("outcome") == "model_overloaded",
        }
        passed = all(checks.values())
        ok += passed
        if not passed:
            why.append(f"{q}: failed {[k for k, v in checks.items() if not v]} "
                       f"(duration_ms={lg.get('duration_ms')}, outcome={lg.get('outcome')})")
    rows["C2"] = (ok, 5, why)

    # C3
    ok, why = 0, []
    for i, (c, q, r) in enumerate(sent):
        if c != "C3":
            continue
        s = (r["json"] or {}) if isinstance(r["json"], dict) else {}
        lg = log_for(i) or {}
        checks = {
            "≤2000ms": (lg.get("duration_ms") or 10**9) <= 2000,
            "1 attempt": lg.get("model_attempts") == 1,
            "0 retries": lg.get("retries") == 0,
            "names key": "GEMINI_API_KEY" in (s.get("error") or ""),
        }
        passed = all(checks.values())
        ok += passed
        if not passed:
            why.append(f"{q}: failed {[k for k, v in checks.items() if not v]} "
                       f"(duration_ms={lg.get('duration_ms')}, attempts={lg.get('model_attempts')})")
    rows["C3"] = (ok, 5, why)

    # C4 — matched in order; a missing line shifts everything after it, so if
    # the counts differ we report how many are missing rather than guessing.
    ok, why = 0, []
    if not aligned:
        why.append(f"{len(sent)} requests sent, {len(logs)} log lines written")
        # Count lines that are individually valid, as an upper bound.
        ok = min(len(sent), sum(1 for lg in logs if lg and all(
            lg.get(k) is not None for k in ("ts", "status", "outcome", "duration_ms"))))
        sent_statuses = [r["status"] for _, _, r in sent]
        logged_statuses = [lg.get("status") if lg else None for lg in logs]
        why.append(f"client statuses: {sent_statuses}")
        why.append(f"logged statuses: {logged_statuses}")
    else:
        for i, (c, q, r) in enumerate(sent):
            lg = logs[i]
            passed = bool(lg) and all(lg.get(k) is not None for k in
                                      ("ts", "status", "outcome", "duration_ms")) \
                and lg.get("status") == r["status"]
            ok += passed
            if not passed:
                why.append(f"{c} {q}: client got {r['status']}, log says "
                           f"{(lg or {}).get('status')}")
    rows["C4"] = (ok, len(sent), why)

    # C5
    ok, why = 0, []
    for c, name, r in sent:
        if c != "C5":
            continue
        passed = r["status"] == 400 and isinstance(r["json"], dict) and "error" in r["json"]
        ok += passed
        if not passed:
            why.append(f"{name}: status {r['status']}, body {r['raw'][:90]!r}")
    rows["C5"] = (ok, 6, why)
    return rows


# ── report ───────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()

    RESULTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    trials, scores = [], []
    for n in range(1, args.trials + 1):
        print(f"trial {n} of {args.trials}", flush=True)
        t = run_trial(stamp, args.label, n)
        trials.append(t)
        scores.append(score(t))

    out = [f"# Capstone run log — {args.label}", "",
           f"`python capstone_eval.py --label {args.label}`, {stamp}, "
           f"{args.trials} trials, cache off, server restarted per scenario.", "",
           "| Criterion | Target | " + " | ".join(f"Run {i}" for i in range(1, args.trials + 1))
           + " | Verdict |",
           "|---|---|" + "---|" * args.trials + "---|"]
    for c in ("C1", "C2", "C3", "C4", "C5"):
        cells = [f"{s[c][0]}/{s[c][1]}" for s in scores]
        met = all(s[c][0] == s[c][1] for s in scores)
        out.append(f"| {TITLES[c]} | {TARGETS[c]} | " + " | ".join(cells)
                   + f" | {'MET' if met else 'MISSED'} |")
    out += ["", "## Why each failure failed", ""]
    for n, s in enumerate(scores, 1):
        for c in ("C1", "C2", "C3", "C4", "C5"):
            for w in s[c][2]:
                out.append(f"- run {n}, {c}: {w}")
    out += ["", "## What the client received (run 1)", "", "```"]
    for c, name, r in trials[0]["sent"]:
        body = r["json"] if isinstance(r["json"], dict) else r["raw"]
        if isinstance(body, dict):
            body = {k: body.get(k) for k in ("error", "error_kind", "fit_card") if k in body} \
                or body
            if isinstance(body.get("selected_item"), dict):
                body["selected_item"] = body["selected_item"].get("id")
        out.append(f"{c} | {name} | {r['status']} | {r['client_ms']}ms | "
                   f"{json.dumps(body, ensure_ascii=False)[:260]}")
    out += ["```", "", "## Server log, run 1", "",
            f"`{trials[0]['log_path'].relative_to(ROOT)}`", "", "```"]
    out += trials[0]["lines"]
    out += ["```", ""]
    path = RESULTS / f"capstone_{stamp}_{args.label}.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[4:12]))
    print(f"\nwrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
