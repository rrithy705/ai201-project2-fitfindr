#!/usr/bin/env python3
"""
Run run_eval.py and score every try against criteria.md.

    python score_eval.py --label before
    python score_eval.py --label after
    python score_eval.py --label before-probe --probes-only

run_eval.py leaves the PASS/FAIL columns blank on purpose. This fills them in
with one check per criterion, written to match the wording in criteria.md, so
the same rule is applied to every try and anyone can re-run the scoring.

It changes nothing in the agent. It wraps suggest_outfit and create_fit_card
to record which item each one was handed (criterion 3 needs that), then calls
run_eval.main() unchanged. run_eval writes its usual results/run_*.md; this
adds results/score_*.md next to it with the filled-in table and the reason
behind every FAIL.
"""

import datetime as dt
import re
import sys

import agent
import config
import run_eval

TARGETS = {1: 4, 2: 5, 3: 5, 4: 4, 5: 5}
TITLES = {
    1: "1. Matching query completes all three tools",
    2: "2. Impossible query stops before tool 2",
    3: "3. Selected item passed correctly between tools",
    4: "4. Fit card has title word, price, platform",
    5: "5. Search results stay within budget",
}

# Title words too generic to count as "distinctive" for criterion 4.
_GENERIC = {"a", "an", "the", "and", "of", "in", "with", "print", "wash"}

_received = {}


def _spy(name, fn):
    def wrapped(*args, **kwargs):
        item = args[0] if name == "suggest_outfit" else args[1]
        _received[name] = item.get("id")
        return fn(*args, **kwargs)
    return wrapped


agent.suggest_outfit = _spy("suggest_outfit", agent.suggest_outfit)
agent.create_fit_card = _spy("create_fit_card", agent.create_fit_card)

_original_run_once = run_eval.run_once


def run_once(scenario, use_trace=True):
    _received.clear()
    record = _original_run_once(scenario, use_trace)
    record["received"] = dict(_received)
    record["scenario"] = scenario
    return record


def _price_in(card: str, price: float) -> bool:
    whole = f"{price:.0f}"
    return re.search(rf"\${whole}(?:\.00)?(?!\d)", card) is not None


def score(criterion, record):
    """(passed, reason) for one try."""
    if record["crashed"]:
        return False, f"crashed: {record['crashed']}"
    s = record["session"]
    got = record["received"]
    card = s.get("fit_card") or ""
    item = s.get("selected_item") or {}

    if criterion == 1:
        if s["error"]:
            return False, f"stopped early: {s['error'][:120]}"
        if "suggest_outfit" not in got or "create_fit_card" not in got:
            return False, "a tool was skipped"
        if not card.strip():
            return False, "fit card empty"
        return True, f"fit card, {len(card)} chars"

    if criterion == 2:
        if got:
            return False, f"called {sorted(got)} after an empty search"
        if not s["error"] or s["fit_card"] is not None:
            return False, "no error message, or a fit card was made"
        if "To find something" not in s["error"]:
            return False, "message doesn't say what to change"
        return True, "stopped after search, message names a change"

    if criterion == 3:
        if s["error"]:
            return False, f"stopped early: {s['error'][:120]}"
        ids = {
            "selected_item": item.get("id"),
            "search_results[0]": (s["search_results"] or [{}])[0].get("id"),
            "suggest_outfit got": got.get("suggest_outfit"),
            "create_fit_card got": got.get("create_fit_card"),
        }
        if len(set(ids.values())) != 1:
            return False, f"ids differ: {ids}"
        if not _price_in(card, item["price"]):
            return False, f"fit card has no ${item['price']:.0f}"
        return True, f"id {item['id']} throughout, ${item['price']:.0f} in card"

    if criterion == 4:
        if s["error"]:
            return False, f"stopped early: {s['error'][:120]}"
        title_words = {
            w for w in re.findall(r"[a-z0-9]+", item["title"].lower())
            if w not in _GENERIC
        }
        card_words = set(re.findall(r"[a-z0-9]+", card.lower()))
        missing = []
        if not title_words & card_words:
            missing.append(f"title word (any of {sorted(title_words)})")
        if not _price_in(card, item["price"]):
            missing.append(f"price ${item['price']:.0f}")
        if item["platform"].lower() not in card.lower():
            missing.append(f"platform {item['platform']}")
        if missing:
            return False, "missing " + ", ".join(missing)
        return True, "title word, price and platform all present"

    if criterion == "probe":
        expect = record["scenario"]["expect"].lower()
        if s["error"] and "No listings matched" in s["error"]:
            return True, "stopped at the empty-search branch"
        if s["error"]:
            return False, f"stopped early: {s['error'][:120]}"
        if expect in item["title"].lower():
            return True, f"picked {item['title']}"
        return False, f"picked {item['title']} (${item['price']:g}) — not {expect}"

    if criterion == 5:
        ceiling = s["parsed"].get("max_price")
        if ceiling is None:
            return False, "parser found no max_price in the query"
        over = [x for x in s["search_results"] if x["price"] > ceiling]
        if over:
            return False, f"{len(over)} result(s) over ${ceiling:g}"
        top = max((x["price"] for x in s["search_results"]), default=0)
        return True, f"{len(s['search_results'])} results, highest ${top:g} ≤ ${ceiling:g}"

    return None, ""


_original_write_report = run_eval.write_report


def write_report(rows, args):
    _original_write_report(rows, args)

    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    label = f"_{args.label}" if args.label else ""
    path = config.RESULTS_DIR / f"score_{stamp}{label}.md"
    n = args.tries

    table = [
        f"| Criterion | Target | {' | '.join(f'Try {i}' for i in range(1, n + 1))} | Verdict |",
        f"|---|---|{'|'.join(['---'] * n)}|---|",
    ]
    probe_table = [table[0].replace("Criterion | Target", "Probe | Query"), table[1]]
    reasons = []
    for row in rows:
        c = row["scenario"].get("criterion")
        if not c and row["scenario"].get("expect"):
            results = [score("probe", r) for r in row["tries"]]
            passes = sum(ok for ok, _ in results)
            cells = " | ".join("PASS" if ok else "FAIL" for ok, _ in results)
            probe_table.append(
                f"| {row['scenario']['name']} | `{row['scenario']['query']}` "
                f"| {cells} | {passes}/{n} |"
            )
            reasons.append(f"**{row['scenario']['name']}** — query `{row['scenario']['query']}`")
            reasons += [f"- Try {i}: {'PASS' if ok else 'FAIL'} — {why}"
                        for i, (ok, why) in enumerate(results, 1)]
            reasons.append("")
            continue
        if not c:
            continue
        results = [score(c, r) for r in row["tries"]]
        passes = sum(ok for ok, _ in results)
        verdict = "MET" if passes >= TARGETS[c] else "MISSED"
        cells = " | ".join("PASS" if ok else "FAIL" for ok, _ in results)
        table.append(
            f"| {TITLES[c]} | {TARGETS[c]} of 5 | {cells} | {verdict} ({passes}/{n}) |"
        )
        reasons.append(f"**{TITLES[c]}** — query `{row['scenario']['query']}`")
        reasons += [f"- Try {i}: {'PASS' if ok else 'FAIL'} — {why}"
                    for i, (ok, why) in enumerate(results, 1)]
        reasons.append("")

    text = "\n".join(
        [f"# Scored run log{f' — {args.label}' if args.label else ''}", "",
         "- Produced by: `score_eval.py` wrapping `run_eval.py::main`",
         f"- When: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
        + table + ["", "## Diagnostic probes (not criteria)", ""] + probe_table
        + ["", "## Why each try passed or failed", ""] + reasons
    )
    path.write_text(text, encoding="utf-8")
    print(f"\nWrote {path.relative_to(config.ROOT)}\n")
    print("\n".join(table))
    print()
    print("\n".join(probe_table))


run_eval.run_once = run_once
run_eval.write_report = write_report

if __name__ == "__main__":
    if "--probes-only" in sys.argv:
        sys.argv.remove("--probes-only")
        run_eval.scenario_module.SCENARIOS[:] = [
            sc for sc in run_eval.scenario_module.SCENARIOS if sc.get("expect")
        ]
    sys.exit(run_eval.main())
