"""
The one place FitFindr talks to the model.

Two of your three tools call out to a service. Everything that does goes
through `generate()` below.

That matters more in unit 3 than it did in unit 1, because an agent run is
several requests rather than one. A student iterating on a loop will cross the
per-minute limit within a few minutes. Rather than three hundred people each
writing their own pacing code, the pacing lives here, once.

What this does for you:

  • Paces requests so you stay under the per-minute limit, and says when it's
    waiting. A pause is the limiter doing its job, not a hang.
  • Reuses answers to prompts already sent, while you're building. Turned off
    for evaluation runs.
  • Stops if a session makes an unreasonable number of calls, rather than
    silently draining your day's allowance. A runaway agent loop is the
    classic way to do that.
  • Retries when the service says you're going too fast.
  • Returns a readable message when the model can't be reached, instead of a
    stack trace. Unit 4 Milestone 2 has you trigger exactly that on purpose.
  • Counts your calls and the tokens they used, so quota — and cost — are
    numbers you can see rather than numbers you multiply off a pricing page.

The model name and the temperature live in config.py, not here.
"""

import hashlib
import json
import os
import re
import sys
import time

import config

_call_times: list[float] = []
_session_calls = 0
_cache_hits = 0
_prompt_tokens = 0
_output_tokens = 0
_client = None
_budget_warned = False
_retries = 0          # CAPSTONE: transient + rate-limit retries this session
_paced_s = 0.0        # CAPSTONE: seconds spent waiting on the per-minute limiter
_backoff_s = 0.0      # CAPSTONE: seconds spent sleeping between retries


class QuotaGuard(Exception):
    """Raised when a session blows through its request budget."""


class ModelUnavailable(Exception):
    """
    Raised when the model can't be reached at all — a bad key, no network, a
    model name that doesn't resolve.

    This exists so your agent can catch one specific thing and say something
    useful, instead of showing a user a stack trace. Unit 4 Milestone 2 has you
    trigger it deliberately by changing one character of your key.

    CAPSTONE: `kind` says which failure it was, so the agent can give advice
    that fits it instead of always blaming the key:

        "auth"        the key was rejected           → check the key
        "not_found"   the model name didn't resolve  → check AI201_MODEL
        "overloaded"  503/500 on every attempt       → wait and try again
        "timeout"     timed out / no connection on every attempt
        "other"       anything else
    """

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


# ─── Cache ───────────────────────────────────────────────────────────────────


def _cache_key(prompt: str, system: str | None, temperature: float) -> str:
    blob = json.dumps(
        [config.MODEL, system or "", prompt, temperature], sort_keys=True
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _cache_read(key: str) -> str | None:
    path = config.CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["response"]
    except Exception:
        return None


def _cache_write(key: str, response: str) -> None:
    config.CACHE_DIR.mkdir(exist_ok=True)
    path = config.CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({"response": response}), encoding="utf-8")


def clear_cache() -> int:
    """Delete every cached response. Returns how many were removed."""
    if not config.CACHE_DIR.exists():
        return 0
    files = list(config.CACHE_DIR.glob("*.json"))
    for f in files:
        f.unlink()
    return len(files)


# ─── Pacing and guards ───────────────────────────────────────────────────────


def _wait_for_slot() -> None:
    """Sleep, if we've used up this minute's allowance."""
    global _paced_s
    now = time.monotonic()
    _call_times[:] = [t for t in _call_times if now - t < 60.0]

    if len(_call_times) < config.REQUESTS_PER_MINUTE:
        return

    sleep_for = 60.0 - (now - _call_times[0]) + 0.1
    if sleep_for > 0:
        # Only worth announcing if it's long enough to notice. Otherwise the
        # message reads "Waiting 0s", which looks like something went wrong.
        if sleep_for >= 1.0:
            print(
                f"  [rate limit] {config.REQUESTS_PER_MINUTE} requests used this "
                f"minute. Waiting {sleep_for:.0f}s. This is normal.",
                file=sys.stderr,
                flush=True,
            )
        time.sleep(sleep_for)
        _paced_s += sleep_for
        _call_times[:] = [t for t in _call_times if time.monotonic() - t < 60.0]


def _check_budget() -> None:
    global _budget_warned
    if _session_calls < config.SESSION_REQUEST_BUDGET:
        return
    if not _budget_warned:
        _budget_warned = True
    raise QuotaGuard(
        f"This session has made {_session_calls} requests, which is the "
        f"budget set in config.py (SESSION_REQUEST_BUDGET).\n"
        f"That usually means a loop is running away rather than that you've "
        f"done {_session_calls} requests' worth of real work.\n"
        f"Stop the program and look for the loop. If you really do need more, "
        f"raise the number in config.py — but look first."
    )


def usage() -> str:
    """One line on what this session has spent. Printed by app.py on exit."""
    tokens = ""
    if _prompt_tokens or _output_tokens:
        tokens = (
            f", {_prompt_tokens} prompt + {_output_tokens} output tokens"
        )
    return (
        f"{_session_calls} model calls this session"
        f"{f', {_cache_hits} served from cache' if _cache_hits else ''}"
        f"{tokens}"
    )


def call_count() -> int:
    return _session_calls


def stats() -> dict:
    """
    CAPSTONE: every counter in one dict, so serve.py can log what one request
    spent by subtracting a snapshot taken before it from one taken after.
    """
    return {
        "model_attempts": _session_calls,
        "retries": _retries,
        "cache_hits": _cache_hits,
        "paced_ms": round(_paced_s * 1000),
        "backoff_ms": round(_backoff_s * 1000),
        "prompt_tokens": _prompt_tokens,
        "output_tokens": _output_tokens,
    }


def token_counts() -> dict:
    """
    What this session actually spent, in tokens, as reported by the service.

    Here's why this exists: a number off the pricing page is an estimate of
    what a run like yours might cost. This is what your run did cost. When you
    write down the cost of one agent run, take it from here.

    Cached answers cost nothing and so add nothing — if you want the real
    per-run numbers, run with the cache off.
    """
    return {
        "prompt": _prompt_tokens,
        "output": _output_tokens,
        "total": _prompt_tokens + _output_tokens,
    }


def _record_tokens(response) -> None:
    """
    Add one response's token counts to the session total.

    The service reports them on `response.usage_metadata`. It is allowed to
    report nothing, or half of it — and a missing count is never a good enough
    reason to kill a run that already succeeded, so anything unexpected here is
    dropped rather than raised.
    """
    global _prompt_tokens, _output_tokens
    try:
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return
        prompt = getattr(meta, "prompt_token_count", None)
        output = getattr(meta, "candidates_token_count", None)
        if isinstance(prompt, int):
            _prompt_tokens += prompt
        if isinstance(output, int):
            _output_tokens += output
    except Exception:  # noqa: BLE001 — counting must never break a working call
        pass


# ─── The call ────────────────────────────────────────────────────────────────


# ─── CAPSTONE: sorting failures ──────────────────────────────────────────────
#
# Before the capstone, generate() retried only rate limits. Everything else —
# including a 503 "model is experiencing high demand", which goes away by
# itself a second later — was raised on the first attempt, and the agent told
# the user to check their key. The unit 4 after run lost 8 of 35 tries to that.
#
# Now each failure is one of:
#   rate_limit  429 / resource exhausted     → wait as long as the service asks
#   transient   503, 500, 502, 504, timeout,  → retry with a short backoff, up
#               connection reset                to TRANSIENT_ATTEMPTS in total
#   permanent   bad key, unknown model, …     → raise at once. Retrying a bad
#                                               key only makes the user wait.

_TRANSIENT_MARKERS = (
    "503", "500", "502", "504", "unavailable", "overloaded", "high demand",
    "internal error", "deadline", "timed out", "timeout", "connection",
    "network", "temporarily",
)


def _classify(exc: Exception) -> str:
    message = str(exc).lower()
    if (
        "429" in message
        or "resource" in message and "exhaust" in message
        or "rate" in message and "limit" in message
    ):
        return "rate_limit"
    # A rejected key is permanent even if the message happens to contain a
    # transient-looking word, so check it first.
    if "api key" in message or "api_key" in message or "unauthenticated" in message \
            or "permission_denied" in message or "401" in message or "403" in message:
        return "auth"
    if "not found" in message or "404" in message:
        return "not_found"
    if any(marker in message for marker in _TRANSIENT_MARKERS):
        return "transient"
    return "other"


def _injected_fault(attempt: int) -> Exception | None:
    """
    CAPSTONE test hook. `AI201_FAULT` makes an attempt fail *before* it goes to
    the network, so the bad path can be tested on demand instead of waiting for
    the service to have a bad day:

        AI201_FAULT=503x1   the first attempt of every call fails with a 503
        AI201_FAULT=503     every attempt fails with a 503 (a real outage)
        AI201_FAULT=401     every attempt fails as a rejected key

    The exception goes through exactly the same handling as a real one. Unset
    (the default) it does nothing. Read on every call so a test can change it.
    """
    spec = os.getenv("AI201_FAULT", "").strip().lower()
    if not spec:
        return None
    code, _, times = spec.partition("x")
    if times and attempt >= int(times):
        return None
    if code == "503":
        return RuntimeError(
            "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is "
            "currently experiencing high demand. (injected by AI201_FAULT)'}}"
        )
    if code == "401":
        return RuntimeError(
            "400 INVALID_ARGUMENT. API key not valid. Please pass a valid API "
            "key. (injected by AI201_FAULT)"
        )
    return None


def _explain(exc: Exception) -> str:
    """Turn a provider exception into something a person can act on."""
    message = str(exc).lower()
    if "api key" in message or "api_key" in message or "unauthenticated" in message:
        return (
            "The model rejected your API key. Check GEMINI_API_KEY in your .env "
            "file, or create a fresh key at aistudio.google.com."
        )
    if "not found" in message or "404" in message:
        return (
            f"The model name '{config.MODEL}' did not resolve. If you changed "
            f"AI201_MODEL in your .env, put it back. Otherwise post in the help "
            f"channel — this is not something you caused."
        )
    if "503" in message or "unavailable" in message or "high demand" in message \
            or "overloaded" in message:
        return (
            f"The model service is overloaded right now (still failing after "
            f"{config.TRANSIENT_ATTEMPTS} attempts). Your key is fine."
        )
    if "connection" in message or "timeout" in message or "timed out" in message \
            or "network" in message:
        return (
            f"Couldn't reach the model: no answer within "
            f"{config.MODEL_TIMEOUT_S:g}s on any of {config.TRANSIENT_ATTEMPTS} "
            f"attempts. Check your internet connection and try again."
        )
    return f"Couldn't reach the model: {exc}"


def _retry_delay(exc: Exception, attempt: int) -> float:
    """
    How long to wait before retrying a call the service pushed back on.

    When you cross the per-minute limit, the service usually says how long it
    wants you to wait — "Please retry in 29.7s", or a retryDelay field. Honour
    that, because the limit is per *minute* and a 1-2-4-8 backoff gives up
    about fifteen seconds in, well before the minute is over. That's the
    difference between a run that pauses and a run that dies.

    Falls back to exponential backoff when the service doesn't say.
    """
    text = str(exc)
    match = (
        re.search(r"retry in (\d+(?:\.\d+)?)\s*s", text, re.I)
        or re.search(r"retryDelay['\"]?\s*:\s*['\"](\d+(?:\.\d+)?)s", text)
    )
    hinted = float(match.group(1)) + 1.0 if match else 0.0
    return min(65.0, max(2.0 ** attempt, hinted))


def _get_client():
    global _client
    if _client is None:
        from google import genai

        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "No GEMINI_API_KEY found.\n"
                "Copy .env.example to .env and paste your key in, then try "
                "again. `python test.py` will confirm it's working."
            )
        from google.genai import types

        # CAPSTONE: a timeout on every request. Without one, a call the service
        # never answers hangs the run — and on serve.py, every request queued
        # behind it. A timeout counts as transient and is retried.
        _client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(
                timeout=int(config.MODEL_TIMEOUT_S * 1000)
            ),
        )
    return _client


def generate(
    prompt: str,
    system: str | None = None,
    cache: bool = True,
    temperature: float | None = None,
) -> str:
    """
    Send a prompt and get text back.

    Args:
        prompt: what you're asking.
        system: an optional instruction about how to behave. This is the
                agent's control surface — when to do what, and what to do with
                nothing. Not a personality setting.
        cache:  reuse an identical earlier answer if there is one. Leave this
                True while building. Pass False when you're evaluating — five
                tries of the same input have to be five real answers.
        temperature: how much the model varies between runs. Defaults to
                config.TEMPERATURE. Pass 0.0 when you want the same answer
                every time.

    Every call in this course goes through here. If you need to change how the
    model is called, change it in this one place.
    """
    global _session_calls, _cache_hits, _retries, _backoff_s

    use_cache = cache and config.CACHE_ENABLED
    temperature = config.TEMPERATURE if temperature is None else temperature
    key = _cache_key(prompt, system, temperature)

    if use_cache:
        hit = _cache_read(key)
        if hit is not None:
            _cache_hits += 1
            return hit

    _check_budget()

    last_error: Exception | None = None
    transient_failures = 0
    for attempt in range(config.MAX_RETRIES):
        _wait_for_slot()
        try:
            client = _get_client()
            _call_times.append(time.monotonic())
            _session_calls += 1

            fault = _injected_fault(attempt)
            if fault is not None:
                raise fault

            call_config = {"temperature": temperature}
            if system:
                call_config["system_instruction"] = system
            kwargs = {
                "model": config.MODEL,
                "contents": prompt,
                "config": call_config,
            }

            response = client.models.generate_content(**kwargs)
            _record_tokens(response)
            text = (response.text or "").strip()

            if use_cache:
                _cache_write(key, text)
            return text

        except Exception as exc:  # noqa: BLE001 — surfaced below
            if isinstance(exc, RuntimeError) and "No GEMINI_API_KEY" in str(exc):
                raise
            last_error = exc
            kind = _classify(exc)

            if kind == "transient":
                transient_failures += 1
                if transient_failures >= config.TRANSIENT_ATTEMPTS:
                    timed_out = any(w in str(exc).lower() for w in
                                    ("timed out", "timeout", "connection", "network"))
                    raise ModelUnavailable(
                        _explain(exc), "timeout" if timed_out else "overloaded"
                    ) from exc
                backoff = config.TRANSIENT_BACKOFF_S * (2 ** (transient_failures - 1))
                _retries += 1
                print(
                    f"  [retry] {type(exc).__name__}: {str(exc).splitlines()[0][:90]} "
                    f"— waiting {backoff:g}s (attempt {transient_failures} of "
                    f"{config.TRANSIENT_ATTEMPTS}).",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(backoff)
                _backoff_s += backoff
                continue

            if kind != "rate_limit":
                raise ModelUnavailable(
                    _explain(exc), "auth" if kind == "auth" else
                    "not_found" if kind == "not_found" else "other"
                ) from exc

            backoff = _retry_delay(exc, attempt)
            _retries += 1
            print(
                f"  [rate limit] service pushed back. Waiting {backoff:.0f}s "
                f"(attempt {attempt + 1} of {config.MAX_RETRIES}). This is "
                f"the limiter doing its job, not a bug.",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(backoff)
            _backoff_s += backoff

    raise RuntimeError(
        f"Still rate limited after {config.MAX_RETRIES} attempts. Wait a "
        f"minute and try again — your key is fine.\nLast error: {last_error}"
    )
