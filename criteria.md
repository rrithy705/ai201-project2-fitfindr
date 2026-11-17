# Acceptance criteria — FitFindr

Five criteria that say what "working" means for this agent, written in unit 3
**before** any results existed.

An acceptance criterion names a target: a number, a count, a rate, or something
a person could plainly observe. *"The agent handles errors"* is an opinion.
*"When search returns nothing, the agent stops before calling the second tool,
in 5 of 5 tries"* is a criterion.

Under each one, write a sentence or two on **why that target** and not a
stricter one. A reason that says something about your tools, your loop, or the
data earns credit; *"80% seemed reasonable"* does not.

> Missing your own targets next unit costs you nothing. Setting a target so
> easy you can't miss it does.

**Two are written for you. You write three.**

---

## 1. A matching query completes all three tools

Given a query that matches at least one listing, the agent completes all three
tool calls and returns a fit card — in at least 4 of 5 tries.

**Why this target:**
I chose 4 out of 5 because the search uses keyword matching, so some search phrases might not find a listing even when a similar item exists. Requiring 5 out of 5 would be too strict because different wording can affect the search results.

---

## 2. An impossible query stops before the second tool

Given a query that matches no listings, the agent stops before calling
`suggest_outfit` and returns a message naming what to change — 5 of 5 tries.

**Why this target:**
I chose 5 out of 5 because the agent has a specific condition that checks whether the search returned any results. If the list is empty, the loop should stop instead of calling the next tool. This is a predictable part of the agent's logic.

---

## 3. The selected item is passed correctly between tools
When search_listings finds an item, the same item is passed to suggest_outfit through the session state: the `id` of `session["selected_item"]` equals the `id` of the first item in `session["search_results"]` and of the item suggest_outfit received, and the price in the fit card equals `session["selected_item"]["price"]` — in 5 out of 5 tries.

**Why this target:**

I chose 5 out of 5 because the session state is designed to keep the selected listing consistent as it moves between the three tools. The search results and selected item are stored in the session dictionary, so the same item should be passed to suggest_outfit every time. Checking the item ID and price makes it possible to verify that the tools are using the same listing rather than a different result.

---

## 4. The fit card includes the important item details
Running the same matching query 5 times (e.g. 'vintage graphic tee under $30'), at least 4 of the 5 fit cards include at least one distinctive word from the selected item's title (e.g. "tee"), the exact price (e.g. "$18"), and the platform name (e.g. "depop", in any capitalization).


**Why this target:**
I chose 4 out of 5 because the fit card uses Gemini, which can generate different responses each time. The card should still include the important shopping information, even if the wording changes.


---

## 5. Search results stay within the user's budget
When a user enters a maximum price, every returned listing must be at or below that price — in 5 out of 5 tries.


**Why this target:**
I chose 5 out of 5 because search_listings uses a price filter to remove items that exceed the user's budget. This is a basic requirement for the shopping agent and should work consistently without depending on the AI model.


---

<!-- ─────────────────────────────────────────────────────────────────────────
     UNIT 4 — read this before you change anything above.

     If a criterion turns out to be BROKEN rather than merely unmet, you can
     revise it, and that earns credit. But never delete or edit the original
     line. Add the revision underneath it, like this:

         ## 4. Something about the fit card

         The fit card is different every time.

         **Why this target:** ...

         > **Revised in unit 4:** For 5 different items, the 5 fit cards share
         > no opening sentence.
         >
         > **Why revised:** "different" wasn't checkable — two cards that
         > differed by one word still counted. The new version is something I
         > can actually score.

     That's a revision because the criterion couldn't be MEASURED.

     Lowering a target because you missed it is not a revision, and it costs
     you the point:

         ✗ "I said the empty search stops it 5 of 5 times, but I got 3 of 5,
            so 3 of 5 is more realistic."

     A number you missed stays where it is, gets diagnosed, and gets a fix
     attempted. That's where the points are.
     ───────────────────────────────────────────────────────────────────────── -->

---

# Capstone criteria — shape B, hardening the model call

Written before any capstone test ran. Every criterion is tested through the
running server (`POST /ask` on `serve.py`) with the response cache off
(`AI201_CACHE=0`), because the first logged session showed the cache
answering a request that had a 503 injected. A **trial** is one fresh start of
the server per scenario and the full set of requests below. Each criterion
gets three trials.

The five matching queries used wherever a criterion says "the five matching
queries": `vintage graphic tee under $30`, `90s track jacket in size M`,
`platform sneakers size 8`, `vintage jeans under $35`,
`denim jacket under $50`.

Criteria C1–C4 are about the extension. C5 is about input handling that
`serve.py` already had.

## C1. A single 503 is retried and the user never sees it

With `AI201_FAULT=503x1` (the first attempt of every model call fails with a
503), each of the five matching queries returns HTTP 200 with
`session["error"]` null and a non-empty `fit_card`, and its log line shows
`retries` = 2 (one per model call) — **5 of 5 in each trial.**

**Why this target:** the unit 4 after run lost 8 of 35 tries to exactly
this, a 503 that would have cleared on a second attempt. The retry is
deterministic code: one failure, then a pause, then a real call. Anything
less than 5/5 means the retry is broken, not unlucky. Requiring `retries` = 2
in the log as well checks that it recovered *by retrying*, rather than the
fault never firing (which is what the cache did in session 1).

## C2. An outage stops quickly, keeps the search, and doesn't blame the key

With `AI201_FAULT=503` (every attempt fails), each of the five matching
queries: returns within **10,000 ms** (`duration_ms` in its log line); keeps the
search result (`selected_item` not null); has an error message that contains
"wait" and does **not** contain "GEMINI_API_KEY"; and is logged with outcome
`model_overloaded` — **5 of 5 in each trial.**

**Why this target:** three attempts with a 1 s then 2 s pause is 3 s of
waiting, plus about 1 s for the MCP search. So 10 s leaves room for a slow
machine but would still catch a retry loop that ran too long or never ended.
The message check is the unit 4 bug itself: a user told to check a working key
goes and breaks it. 5/5 because none of this depends on the model. The fault
is injected before the network.

## C3. A rejected key is not retried

With `AI201_FAULT=401`, each of the five matching queries returns within
**2,000 ms**, its log line shows `model_attempts` = 1 and `retries` = 0, and the
error message contains "GEMINI_API_KEY" — **5 of 5 in each trial.**

**Why this target:** this is the risk the new layer adds. If a permanent error
were mistaken for a transient one, a bad key would cost three attempts and
3 s of backoff before saying anything, and it could never succeed. 2,000 ms
is the search (~1 s) plus one failed call, with no room for even one 1 s
backoff. `model_attempts` = 1 checks the same thing directly.

## C4. Every request leaves exactly one log line, failures included

Across every request a trial sends (all of C1, C2, C3 and C5, 21 requests),
the log gains exactly one line per request. Each line parses as JSON, has
non-null `ts`, `status`, `outcome` and `duration_ms`, and its `status` equals
the HTTP status the client actually received — **21 of 21 in each trial.**

**Why this target:** a log that misses the failures is worse than none,
because it says the bad path never happened. The rows most likely to go
missing are the ones that fail early (rejected input) or crash, which is
exactly why they're included. One missing line means a class of request
can't be seen, so the target is all of them.

## C5. Malformed input gets a 400, never a 500

Six malformed requests: no body; a body that isn't JSON; `{"query": ""}`;
`{"query": "   "}`; `{"query": 42}`; and a JSON array `["vintage tee"]`. Each
returns HTTP **400** with a JSON body that has an `error` field — **6 of 6 in
each trial.**

**Why this target:** each of these is the caller's mistake, and a 400 tells
them so and what to send. A 500 tells them the server broke, and a script
calling FitFindr would retry it forever. None of this touches the model, so
it should hold every time; 5 of 6 would mean one shape of bad input crashes
the server.
