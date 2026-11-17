#!/usr/bin/env python3
"""
FitFindr over HTTP. ← UNIT 9

    python serve.py                       run it on your machine
    gunicorn serve:app                    run it the way a host runs it

Everything else in this repo exits after one command. A host has nothing to
keep running, so a command line cannot be deployed. This file is the smallest
thing that can: it starts a web server, waits, and hands each request to the
same `run_agent()` your CLI calls. **No new agent logic lives here.** If your
loop works from `python app.py ask`, it works from here; if it doesn't, fix it
there, not in this file.

Two routes:

    POST /ask       {"query": "vintage graphic tee under $30",
                     "wardrobe": {...}}     ← wardrobe is optional
    GET  /health    is it awake?

`/ask` returns the session dict from `run_agent()` as JSON, unchanged — the
same keys you print from the command line, including `error`. Read
`session["error"]` first, exactly as you do everywhere else.

It runs **one request at a time**, and one route is deliberately slower than a
web server has to be. The reason is worth reading before you deploy: see the
note above `_one_at_a_time` below — it also decides which gunicorn worker you
can use.

CAPSTONE: every POST /ask now appends one JSON line to logs/requests.jsonl
(or wherever AI201_LOG points) — including requests that were rejected or
crashed. The fields are listed above `_log` below.
"""

import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# config first, and before anything that talks to the model: it loads your .env
# and fixes the Windows console encoding for every module that imports it.
import config  # noqa: F401

from flask import Flask, jsonify, request

import generate
from agent import run_agent
from utils.data_loader import get_example_wardrobe

app = Flask(__name__)


# ── CAPSTONE: the structured log ──────────────────────────────────────────────
# One JSON object per line, one line per request, appended as the request
# finishes. A file you can read back with `json.loads`, not print().
#
#   ts              when the request arrived, UTC, ISO 8601
#   request_id      8 hex chars, to find one request again
#   body            the raw request body, first 200 chars — what came in
#   query           the query field, if there was a usable one
#   status          the HTTP status sent back
#   outcome         ok | empty_search | no_item_words | model_overloaded |
#                   model_timeout | model_auth | model_not_found | model_other |
#                   search_unavailable | bad_request | server_error
#   selected_id     the listing the agent picked (None if it stopped first)
#   fit_card_chars  length of the fit card — what came out (0 if none)
#   error           first line of the error, if any
#   duration_ms     arrival to response, including any wait for the lock
#   model_attempts  model calls attempted, failed ones included
#   retries         how many of those were retries (transient or rate limit)
#   prompt_tokens / output_tokens   as reported by the service — the cost
#   fault           AI201_FAULT, if a failure was being injected

LOG_PATH = Path(os.getenv("AI201_LOG", config.ROOT / "logs" / "requests.jsonl"))
_log_lock = threading.Lock()


def _log(record: dict) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _log_lock, LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:  # a full disk must not take the answer down with it
        print(f"  [serve] couldn't write the log: {exc}", file=sys.stderr, flush=True)


# ── one request at a time ─────────────────────────────────────────────────────
# Here's why this exists.
#
# A web server will happily run two requests at once. Two things in this repo
# assume otherwise:
#
#   • If you moved a tool onto MCP in unit 4, `mcp_client.call_tool` starts
#     `mcp_server.py` as a separate process over stdio, one per call. Two
#     overlapping requests means two extra Python interpreters, and the free
#     tier you're deploying to has 512 MB for all of it. That is the reason
#     that would still be here even if everything else were perfect.
#   • `generate.py`'s pacing window and its call counter are plain module
#     globals — deliberately, because that file is teaching pacing and quota,
#     not locking. Two threads sharing them means the per-minute limiter is
#     counting something that isn't true.
#
# What the lock covers is exactly the agent run: the part that spawns
# processes and calls the model. Reading the request, rejecting a bad one, and
# turning the answer into JSON all happen outside it — so a request with a
# malformed body comes straight back with a 400 instead of queueing behind
# somebody else's agent.
#
# Serialising the runs costs you nothing here — this is one user asking one
# question — and it keeps the deployed behaviour identical to the CLI's. When
# that stops being an acceptable trade, the fix is a real queue, not a bigger
# lock.
#
# The same constraint decides your start command, and this is the part that
# bites in deployment rather than on your machine. `mcp_client.call_tool`
# wraps `asyncio.run()`, and `asyncio.run()` refuses to start when an event
# loop is already running. An async worker always has one running. So under
# `gunicorn -k gevent` (or `-k eventlet`, or `serve:app` wrapped for an ASGI
# server like uvicorn) EVERY MCP call fails with "asyncio.run() cannot be
# called from a running event loop" — not some of them under load, all of
# them, every time, in a place your laptop never showed you.
#
#     gunicorn serve:app              ← right: the DEFAULT sync worker
#     gunicorn -k gevent serve:app    ← breaks every MCP call you make

_one_at_a_time = threading.Lock()


@app.get("/health")
def health():
    """Is the server awake? A host pings something like this to find out."""
    return jsonify({"status": "ok"})


@app.post("/ask")
def ask():
    """
    Run the agent on one query, and log it whatever happens.

    In:   {"query": "...", "wardrobe": {...}}   wardrobe optional — leave it
                                                out and you get the same
                                                example wardrobe the CLI uses.
    Out:  the session dict from run_agent(), as JSON.
    """
    started = time.perf_counter()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "request_id": uuid.uuid4().hex[:8],
        "body": request.get_data(as_text=True)[:200],
        "query": None,
        "status": 500,
        "outcome": "server_error",
        "selected_id": None,
        "fit_card_chars": 0,
        "error": None,
        "duration_ms": None,
        "model_attempts": 0,
        "retries": 0,
        "prompt_tokens": 0,
        "output_tokens": 0,
        "fault": os.getenv("AI201_FAULT") or None,
    }
    try:
        response, status = _ask(record)
        record["status"] = status
        return response, status
    except Exception as exc:
        # Anything that escapes still gets a line. Flask turns it into a 500.
        record["error"] = f"{type(exc).__name__}: {exc}"[:300]
        raise
    finally:
        record["duration_ms"] = round((time.perf_counter() - started) * 1000)
        _log(record)


def _ask(record: dict):
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    if not query:
        # 400 rather than a stack trace: the caller can act on this one.
        record["outcome"] = "bad_request"
        record["error"] = "no query"
        return jsonify({"error": "Send JSON with a 'query' field, e.g. "
                                 '{"query": "vintage graphic tee under $30"}'}), 400
    record["query"] = query

    wardrobe = payload.get("wardrobe")
    if not isinstance(wardrobe, dict):
        wardrobe = get_example_wardrobe()

    # A queued request should look like a queued request. Without this the
    # second caller just sits there, and "slow" and "waiting its turn" are
    # indistinguishable from the outside — which is how people conclude the
    # deployment is broken when it is behaving exactly as designed.
    #
    # `locked()` can be a moment out of date, so the note is occasionally
    # missed — which costs nothing, because nothing depends on it.
    if _one_at_a_time.locked():
        print(
            "  [serve] another request is still running. This one is waiting "
            "its turn — serve.py handles one at a time, on purpose.",
            file=sys.stderr,
            flush=True,
        )

    failure = None
    session = None
    with _one_at_a_time:
        # Inside the lock, so the difference is this request's spend alone.
        before = generate.stats()
        try:
            session = run_agent(query, wardrobe)
        except Exception as exc:  # noqa: BLE001 — a 500 with a sentence beats a hang
            failure = f"{type(exc).__name__}: {exc}"
        after = generate.stats()
    for k in ("model_attempts", "retries", "prompt_tokens", "output_tokens"):
        record[k] = after[k] - before[k]

    # Outside the lock: building a response is not work the next caller should
    # be waiting on.
    if failure is not None:
        record["error"] = failure[:300]
        return jsonify({"error": failure}), 500

    record["selected_id"] = (session.get("selected_item") or {}).get("id")
    record["fit_card_chars"] = len(session.get("fit_card") or "")
    if session.get("error"):
        record["outcome"] = session.get("error_kind") or "error"
        record["error"] = session["error"].splitlines()[0][:300]
    else:
        record["outcome"] = "ok"
    return jsonify(session), 200


if __name__ == "__main__":
    # PORT and 0.0.0.0 are not decoration. A host tells you which port to
    # listen on through PORT, and it reaches your process from outside the
    # container — bind 127.0.0.1 and nothing but the container itself can
    # connect, which looks exactly like a broken app from the browser.
    port = int(os.getenv("PORT", "5000"))

    # Never on by default. Flask's debugger executes code typed into a browser,
    # and a deployed app with it on is a stranger's shell. Set AI201_DEBUG=1 in
    # your own terminal when you want the reloader.
    debug = os.getenv("AI201_DEBUG", "0") == "1"

    print(f"\nFitFindr is listening on http://localhost:{port}")
    print("It runs one request at a time — a second one waits for the first.")
    print("Ask it something (single quotes, as always):\n")
    print(
        f"  curl -X POST http://localhost:{port}/ask \\\n"
        f"    -H 'Content-Type: application/json' \\\n"
        f"    -d '{{\"query\": \"vintage graphic tee under $30\"}}'\n"
    )
    print("Ctrl-C to stop.\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
