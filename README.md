# FitFindr

> ### 👋 Start here
>
> **New to this repo? Read [RUNNING.md](RUNNING.md) first** — setup, every
> command, and what to do when something breaks.
>
> Once `python test.py` passes:
>
> ```bash
> python app.py listings --full -n 6      # read the data (Milestone 1)
> python app.py fields                    # what you can filter on
> python app.py ask 'vintage graphic tee under $30'
> ```
>
> All three tools are stubs, so that last command will do nothing useful yet.
> That's the starting position.
>
> **The rest of this file is your submission.** Fill it in as you go.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     HOW TO USE THIS FILE

     This is your submission. Fill each section in as you finish the milestone
     it belongs to — don't leave it all to the end.

     Unit 3 asks for the first five sections. Unit 4 adds the five below them.
     Leave the unit 4 sections alone until then; they're here so you know
     what's coming.

     Everything is pasted as TEXT. No screenshots, no images, no video links.
     A typed block of output gets full credit; a picture of the same output
     gets none.
     ───────────────────────────────────────────────────────────────────────── -->

<!-- ═══════════════════════ UNIT 3 — THE BUILD ═══════════════════════ -->

## What This Does

You type what you're after in plain language, such as `vintage graphic tee under $30`
or `platform sneakers size 8`. FitFindr pulls a description, a size and a price
ceiling out of that and searches 40 thrift listings from Depop, ThredUp and
Poshmark. It takes the best match, suggests two outfits that pair it with pieces
you already own (or with common basics if your wardrobe is empty), and writes a
short caption you could post with it. If nothing matches, it stops before
styling anything and tells you which part of your query to change.

---

## Tool Inventory

<!-- Four lines per tool. This is worth 2 points and it's the single most
     common place students lose them.

     "Returns a list" earns NOTHING. The description has to say what is IN
     the list.

     The empty case isn't optional either — it's the thing your loop branches
     on, and if you don't decide it here you'll discover it as a crash in
     Milestone 5. -->

### `search_listings`

- **What it does:** Filters `data/listings.json` by price and size, then ranks what's left by keyword overlap with the description. A word in the title, category or style tags scores 2; a word in the description text, colors or brand scores 1. Stopwords like "a", "for", "looking" and "under" are ignored, and a trailing plural "s" is dropped, so "tees" matches "tee".
- **Inputs:** `description` (str, the words describing the item), `size` (str or None; None skips the size filter), `max_price` (float or None, inclusive; None skips the price filter).
- **Size rule:** whole-token match, not substring. Every token of the requested size has to appear as a whole token in the listing's size, so `M` matches `M`, `S/M` and `M/L` but not `XL`, `L` doesn't match `XL (oversized)`, and `8` matches `US 8` but not `US 8.5`. Listings sized "One Size" match any requested size.
- **Returns:** `list[dict]`, at most `config.SEARCH_RESULT_LIMIT` (10) listing dicts, highest score first, with the cheaper item first on a tie. Each dict is the whole listing: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`.
- **When it has nothing:** `[]`, an empty list, never None and never an exception. That includes a description made up only of stopwords.

### `suggest_outfit`

- **What it does:** Asks the model for two outfits built around the new item. With a wardrobe, the outfits have to use pieces the user owns, named exactly as they appear in the wardrobe.
- **Inputs:** `new_item` (dict, one listing dict as returned by `search_listings`), `wardrobe` (dict with key `items`: a list of dicts, each with `id`, `name`, `category`, `colors`, `style_tags`, `notes`).
- **Returns:** `str`, two outfit ideas of one or two sentences each, as plain text from the model.
- **When it has nothing:** If `wardrobe["items"]` is empty (or the wardrobe is None), it doesn't fail. It asks for two outfits made from common basics and names them (for example "straight-leg blue jeans"), so it still returns a non-empty string.

### `create_fit_card`

- **What it does:** Asks the model for a 2–4 sentence caption about the find and the outfit, mentioning the price and platform once each, in a person's voice rather than a product listing's, with at most two emoji.
- **Inputs:** `outfit` (str, the text returned by `suggest_outfit`), `new_item` (dict, the same listing dict that went into `suggest_outfit`).
- **Returns:** `str`, the caption text only. Because temperature is 0.9, the same input gives different wording each time once the cache is off.
- **When it has nothing:** If `outfit` is empty or only whitespace, it returns this exact string without calling the model: `"Can't write a fit card without an outfit — suggest_outfit returned nothing for this item."`

---

## Planning Loop

<!-- Your branch rule, stated as a rule — the condition AND both paths — plus
     the file and function that holds it.

     Like this:
       "If search_listings returns an empty list, put a message in the session
        and stop. Otherwise take the first result and go to suggest_outfit."
        — agent.py::run_agent

     The grader checks your code against what you claim here, so the file and
     function have to be real. -->

**Branch rule:** If `search_listings` returns an empty list, write a message
into `session["error"]` that names which filter to change, then stop. The loop
never calls `suggest_outfit` or `create_fit_card`, and `fit_card` stays None.
Otherwise, put the first result in `session["selected_item"]` and go to
`suggest_outfit`.

To write that message, `_empty_search_message` re-runs the search with one
filter dropped at a time. That lets it say "raise your max price — 2 match
without the $10 limit, the cheapest at $15" or "drop the size — 5 match in
other sizes". If neither helps, it says the words themselves match nothing and
suggests broader ones.

There's a second, smaller branch: if the query has no item words left after
parsing (e.g. `under $20 size M`), the loop stops before searching and asks
what kind of item you want.

**Where it lives:** `agent.py::run_agent` (the message comes from `agent.py::_empty_search_message`)

**How it decides:** `run_agent` is a `while` loop that runs until
`fit_card` or `error` is set. On each pass it checks which session fields are
still empty and runs the next step: parse → search → suggest_outfit →
create_fit_card. Every pass calls `trace.check_iterations()`, so the loop
can't run past `config.MAX_ITERATIONS`.

**How the query is parsed:** Regex, in `agent.py::parse_query`. A price is a
number after `under`, `below`, `less than`, `max`, `up to` or `<`, or after a
bare `$`. A size has to follow the word `size` (`size M`, `size 8`,
`size W30`, `size one size`). Whatever is left becomes the description. A
query with no price or size gets None for that field, so the search skips
that filter.

**What moves through the session:** in this order
1. `query`: the raw text
2. `parsed`: `{description, size, max_price}`, read by the search step
3. `search_results`: the full list `search_listings` returned
4. `selected_item`: `search_results[0]`, read from the session by both `suggest_outfit` and `create_fit_card`
5. `outfit_suggestion`: read from the session by `create_fit_card`
6. `fit_card`, or `error` if the run stopped early

No value passes straight from one tool call into the next. Each step writes
its result into the session, and the next step reads it back from there.

---

## Sample Run

<!-- Two things go here.

     1. One FULL query and its output, pasted as text.
     2. Your three per-tool terminal tests — the command and what it printed. -->

**One full query**

```
$ python app.py ask 'vintage graphic tee under $30'

  Found:    Y2K Baby Tee — Butterfly Print — $18.0 on depop

  Outfit:   **Outfit 1**
Pair the baby tee with the baggy straight-leg jeans, dark wash and the chunky white sneakers for a classic Y2K contrast of fitted and loose silhouettes. Layer the vintage black denim jacket on top to tie in the cool tones.

**Outfit 2**
Style the baby tee tucked into the wide-leg khaki trousers, accented by the brown leather belt. Finish the look with the black combat boots to ground the soft pink and purple butterfly print.

  Fit card: Scored this Y2K butterfly baby tee on Depop for just $18 and I’m obsessed with the pink and purple print. Whether I'm balancing the fitted silhouette with baggy dark wash denim or tucking it into wide-leg khakis, it's the ultimate nostalgia piece. 🦋

2 model calls this session, 523 prompt + 161 output tokens
```

**The empty-search branch**

```
$ python app.py ask 'designer ballgown size XXS under $5'

  No listings matched 'designer ballgown' in size XXS under $5. To find something, try different words for the item — nothing in the listings matches those words at any size or price. Broader terms like 'tee', 'jacket', 'jeans' or 'sneakers' cover more of the data.

0 model calls this session
```

```
$ python app.py ask 'graphic tee size M under $10'

  No listings matched 'graphic tee' in size M under $10. To find something, raise your max price — 2 match without the $10 limit, the cheapest at $15.
```

**The three tools, tested one at a time**

```
$ python -c "from tools import search_listings; print([(x['title'], x['size'], x['price']) for x in search_listings('graphic tee', max_price=30)])"
[('Y2K Baby Tee — Butterfly Print', 'S/M', 18.0), ('Vintage Band Tee — Faded Grey', 'L', 19.0), ('Graphic Tee — 2003 Tour Bootleg Style', 'L', 24.0), ('Mesh Long-Sleeve Top — Black', 'S/M', 15.0), ('Vintage Graphic Hoodie — Faded Black', 'L', 26.0), ('Oversized Crewneck Sweatshirt — Vintage Navy', 'XL (fits oversized)', 20.0), ('Low-Rise Cargo Pants — Khaki', 'W29', 27.0)]

$ python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
[]
```

```
$ python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, load_listings; print(suggest_outfit(load_listings()[0], get_example_wardrobe()))"
**Outfit 1:** Pair the Levi's 501s with the white ribbed tank top, black cropped zip hoodie, and black combat boots. Cinch it all together with the brown leather belt and add the black crossbody bag.

**Outfit 2:** Style the jeans with the oversized grey crewneck sweatshirt and chunky white sneakers. Layer on the vintage black denim jacket and finish the look with the black crossbody bag.
```

Run three times on the same item with the cache off (`AI201_CACHE=0`), to check
the captions aren't identical:

```
$ AI201_CACHE=0 python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(create_fit_card('jeans and white sneakers', load_listings()[0]))"
Scored these vintage Levi's 501s for just $38 on depop and they fit like an absolute dream. Paired them with crisp white sneakers for that effortlessly lived-in, everyday streetwear feel. Trust me, you can't beat a classic medium wash. 👖👟

Scored these vintage Levi’s 501s on depop for just $38 and they fit like an absolute dream. Kept it classic with crisp white sneakers for that effortless, off-duty coffee run vibe. 👖👟

Scored these vintage Levi's 501s for just $38 on Depop. Paired them with crisp white sneakers for that effortlessly worn-in, off-duty streetwear look. Classic denim never misses 👖✨
```

---

## How I Used AI

<!-- Two specific moments. What you asked, what came back, what you changed.

     "I used Claude to help me code" is not enough.

     "I gave Claude my search_listings spec. It returned None on no match
     instead of an empty list, so I changed it" is the level we want. -->

**Moment 1**

- *What I asked for:* I asked AI to review my third acceptance criterion and check if it was specific and testable.I
- *What came back:* AI said the criterion was mostly testable, but it did not clearly explain how to verify that the same item was passed between the tools.
- *What I changed:* I changed the criterion to have a tester compare the id of session["selected_item"] with the first item in session["search_results"] and with the item received by suggest_outfit. I also added a check that the price in the fit card matches session["selected_item"]["price"].

**Moment 2**

- *What I asked for:* I asked AI to review my fourth acceptance criterion and help make it more measurable and testable.
- *What came back:* AI said my original criterion was too vague because the fit card is generated by Gemini and can have different wording each time.
- *What I changed:* I changed the criterion to run the same query five times and require at least 4 of the 5 fit cards to include a distinctive title word, the exact price, and the platform name. This gives me specific details that I can check in each generated card.

<!-- ═══════════════════════ UNIT 4 — THE TEST ═══════════════════════

     Don't fill these in during unit 3.
     ═══════════════════════════════════════════════════════════════════ -->

---

## Run Log — Before

<!-- Five criteria, five tries each, in this exact format.

     Five, because your criteria are written out of five. Mark each try PASS
     or FAIL, count the passes, and read that count against your target — a
     row targeting 4 of 5 with three PASS cells is MISSED (3/5).

     `python run_eval.py --label before` runs everything and writes the table
     into results/. Paste it here and fill in the verdicts. -->

Produced by `python score_eval.py --label before`. That runs
`run_eval.py::main` unchanged (every scenario in `scenarios.py`, 5 tries each,
cache off, temperature 0.9, 50 real model calls). It then marks each try PASS
or FAIL with one check per criterion, written to match `criteria.md`
(`score_eval.py::score`). Full output is in [results/run_2026-10-13_1920_before.md](results/run_2026-10-13_1920_before.md), and the
reason for every PASS/FAIL is in [results/score_2026-10-13_1920_before.md](results/score_2026-10-13_1920_before.md).

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1. Matching query completes all three tools | 4 of 5 | PASS | PASS | PASS | PASS | PASS | MET (5/5) |
| 2. Impossible query stops before tool 2 | 5 of 5 | PASS | PASS | PASS | PASS | PASS | MET (5/5) |
| 3. Selected item passed correctly between tools | 5 of 5 | PASS | PASS | PASS | PASS | PASS | MET (5/5) |
| 4. Fit card has title word, price, platform | 4 of 5 | PASS | PASS | PASS | PASS | PASS | MET (5/5) |
| 5. Search results stay within budget | 5 of 5 | PASS | PASS | PASS | PASS | PASS | MET (5/5) |

Scenario per criterion (`scenarios.py`): 1 → `90s track jacket in size M`;
2 → `designer ballgown size XXS under $5`; 3 → `platform sneakers size 8`;
4 → `vintage graphic tee under $30` (the query criterion 4 names);
5 → `vintage jeans under $35`. The empty-wardrobe diagnostic
(`denim jacket under $50`, empty wardrobe) completed 5 of 5 times with a
non-empty outfit and fit card.

How each try was scored:
1. PASS if no error, `suggest_outfit` and `create_fit_card` were both called, and the fit card is non-empty.
2. PASS if neither model tool was called, `fit_card` is None, and `session["error"]` names something to change.
3. PASS if the `id` of `selected_item`, `search_results[0]`, the item `suggest_outfit` received and the item `create_fit_card` received are all equal, AND the fit card contains `$<selected_item price>`. The ids come from a wrapper that records each tool's argument.
4. PASS if the card contains a word from the item's title, the exact price (`$18`), and the platform (any case).
5. PASS if the parser found a `max_price` and every listing in `search_results` is at or under it.

Model tries did differ: the five criterion-4 fit cards opened with "Found
this…", "Scored this…" and so on, and were 191 to 356 characters long. So these
are five real answers, not cache hits.

**Real output from one try each.** These are try 1 from `results/run_2026-10-13_1920_before.md`. The loop is
`agent.py::run_agent`, the outfit comes from `tools.py::suggest_outfit`, the
card from `tools.py::create_fit_card`, and the search from `search_listings`
in `mcp_server.py` (called via `mcp_client.call_tool`).

Criterion 1 (`90s track jacket in size M`):
```
- selected_item: 90s Track Jacket — Navy/White Stripe ($45.0, poshmark)
- search_results: 5
Fit card:
Scored this vintage Champion track jacket on Poshmark for just $45 and it’s basically my new uniform. Whether I’m throwing it over a ribbed tank or layering it on top of an oversized crewneck, that navy and white stripe hits that 90s athletic vibe just right. 👟✨
```

Criterion 2 (`designer ballgown size XXS under $5`), from `agent.py::_empty_search_message`:
```
- stopped early: yes — No listings matched 'designer ballgown' in size XXS under $5. To find something, try different words for the item — nothing in the listings matches those words at any size or price. Broader terms like 'tee', 'jacket', 'jeans' or 'sneakers' cover more of the data.
- selected_item: (none)
- search_results: 0
[3] branch
      →    search returned []: stopping before suggest_outfit
```

Criterion 3 (`platform sneakers size 8`). Scorer: `PASS — id lst_019 throughout, $48 in card`
```
- selected_item: Platform Sneakers — White Chunky Sole ($48.0, poshmark)
[3] select_item
      out: Platform Sneakers — White Chunky Sole ($48.0, poshmark)
      →    id lst_019, first of the results
Fit card:
Channeling major Y2K streetwear energy with these white chunky sole platform sneakers, priced at just $48 on Poshmark. Style them effortlessly with dark wash baggy jeans and a vintage denim jacket, or lean into a casual silhouette with wide-leg trousers and a black cropped zip hoodie. Snag this versatile pair to instantly ground your everyday rotation 👟✨
```

Criterion 4 (`vintage graphic tee under $30`). "baby"/"tee"/"butterfly", "$18" and "Depop" are all present:
```
- selected_item: Y2K Baby Tee — Butterfly Print ($18.0, depop)
Fit card:
Found this Y2K butterfly baby tee on Depop for just $18 and I'm obsessed with the pink and purple print. Styling it two ways: super casual with baggy dark wash denim and a black jacket, or dressed down with khaki trousers and combat boots. Which vibe are you wearing? 🦋
```

Criterion 5 (`vintage jeans under $35`). Scorer: `PASS — 10 results, highest $30 ≤ $35`
```
[1] parse_query
      in:  vintage jeans under $35
      out: {'description': 'vintage jeans', 'size': None, 'max_price': 35.0}
[2] search_listings (via MCP)
      in:  {'description': 'vintage jeans', 'size': None, 'max_price': 35.0}
      out: 10 items: Straight Leg Black Jeans — Faded, Leather Belt — Brown, Braided, Bucket Hat — Reversible, Brown Plaid … +7 more
      →    10 match(es)
```

---

## Verdicts and Diagnoses

<!-- MET or MISSED per criterion against LAST UNIT's target, plus a sentence on
     how you decided.

     Then, for every miss: which of the four places it happened — a tool, the
     loop's branch, the session, or the model's output — AND the mechanism.

     Not a diagnosis:  "The fit card was bad."
     A diagnosis:      "The fit card criterion missed on 2 of 5 items. Both had
                        an empty brand field. My prompt puts the brand in the
                        first sentence, so the card opened with a blank and read
                        like a fragment. The tool worked; the prompt assumed a
                        field that isn't always there."

     Look for a pattern. Three misses on the same tool is one problem, not
     three. -->

| # | Criterion | Target | Verdict | How I decided |
|---|---|---|---|---|
| 1 | Matching query completes all three tools | 4 of 5 | **MET (5/5)** | All 5 tries called search → suggest_outfit → create_fit_card and returned a non-empty card. 5 ≥ 4. |
| 2 | Impossible query stops before tool 2 | 5 of 5 | **MET (5/5)** | All 5 tries stopped at step 3 (`branch`), with 0 model calls and a message naming what to change. |
| 3 | Selected item passed correctly between tools | 5 of 5 | **MET (5/5)** | All 5 tries had `lst_019` as `selected_item`, `search_results[0]`, and the argument both model tools received. All 5 cards said `$48`. |
| 4 | Fit card has title word, price, platform | 4 of 5 | **MET (5/5)** | All 5 cards had a title word ("baby"/"tee"/"butterfly"), `$18` and "Depop". 5 ≥ 4. |
| 5 | Search results stay within budget | 5 of 5 | **MET (5/5)** | All 5 tries parsed `max_price` 35.0. The highest result price was $30. |

**Diagnoses**

Nothing missed, so there is no miss to diagnose. Read plainly, though, that is
mostly because **my targets were low**, and I'd rather say so than call it a
good result:

- **Criteria 2, 3 and 5 test code with no model in it.** The parser, the
  search and the branch are deterministic. Running them five times gives the
  same answer five times. The only thing those three rows could fail on is a
  bug, and those bugs were already fixed in unit 3.
- **Criterion 3 passes almost by construction.** `selected_item` is
  `search_results[0]` in the same dict, and both model tools are handed that
  same object. It could only fail if I rewrote the loop. It's a regression
  test, not a measurement.
- **Criteria 1 and 4 are the only rows with real variance**, because of the
  model. Even there, the prompt for `create_fit_card` literally says "Mention
  the price ($18) and the platform (depop)". So the model was being asked to
  do exactly what criterion 4 checks for.
- **Each criterion ran on one query.** Criterion 2's impossible query
  (`designer ballgown size XXS under $5`) shares no word with any listing, so
  it's the easiest possible impossible query.

**The criteria I'd tighten: 1 and 2.** Criterion 1 counts any completed fit
card as a pass, whether or not the item is what the user asked for. Criterion 2
only tests a query with zero words in common with the data. To check whether
the criteria were hiding a failure, I added three **diagnostic probes** to
`scenarios.py`. They are not criteria, and I did not edit `criteria.md`. Each
one passes only if the agent either stops at the empty-search branch or picks
an item whose title contains the word asked for. I ran them on the unchanged
code (`python score_eval.py --label before-probe --probes-only`, see
`results/score_*_before-probe.md`):

| Probe | Query | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Result |
|---|---|---|---|---|---|---|---|
| colour word vs item type | `black boots` | FAIL | FAIL | FAIL | FAIL | FAIL | 0/5 |
| material word vs item type | `leather jacket under $45` | FAIL | FAIL | FAIL | FAIL | FAIL | 0/5 |
| impossible item with a common colour | `black ballgown` | FAIL | FAIL | FAIL | FAIL | FAIL | 0/5 |

What happened, from `results/run_*_before-probe.md`:

```
black boots               → picked Biker Shorts — Black, Shiny ($14)    (Suede Chelsea Boots, $44, exist in the data)
leather jacket under $45  → picked Leather Belt — Brown, Braided ($12)  (Denim Jacket $42 and Track Jacket $45 are in budget)
black ballgown            → picked Biker Shorts — Black, Shiny ($14)    (no ballgown exists; should have stopped)

Fit card (black boots, try 1):
Serving major Y2K off-duty energy with these shiny black biker shorts. Snagged them on Depop for just $14 and they're the ultimate base for a sporty zip-hoodie fit or an edgy oversized crewneck look. 🖤✨
```

All 15 of those runs would have **passed criterion 1**: all three tools ran
and returned a fit card. The `black ballgown` runs show the branch from
criterion 2 never firing on an impossible request.

**Diagnosis: one problem, not three. It's in the tool, `tools.py::search_listings` → `_score`.**
Every query word scores the same, whatever role it plays. An adjective
("black", "leather") in a listing's title scores 2, exactly what the item
noun ("boots", "jacket") scores in a title. So a listing that matches only
the adjective ties with one that is actually the item, and price breaks the
tie. Then:

- `black boots`: Biker Shorts — Black score 2 ("black" in the title). Suede
  Chelsea Boots score 2 ("boots" in the title). That's a tie, and the
  tie-break (cheaper first) picks the $14 shorts over the $44 boots.
- `leather jacket`: the Leather Belt scores 2 ("leather") and the Denim Jacket
  scores 2 ("jacket"). Same tie, and the $12 belt wins.

  (Checked with `tools._score` directly: both pairs come out 2–2.)
- `black ballgown`: "ballgown" matches nothing, but "black" matches plenty.
  A listing only needs a score above zero to be kept, so the list is
  non-empty and **the branch in `agent.py::run_agent` never sees `[]`**.
  The loop and the session did their jobs correctly. The tool returned a
  non-empty list that meant "nothing you asked for".

The model is not the cause. `suggest_outfit` and `create_fit_card` faithfully
styled the wrong item they were handed, and the card read well. That is
worse, because nothing on screen tells the user the search went wrong.

---

## Loop Trace

<!-- One full run, printed step by step, with the MCP call visible in it.

     `python app.py ask '...' --trace` once you've added the trace.step()
     calls in Milestone 2.

     Worth pasting BOTH the happy path and the empty-search path. The empty
     one should be visibly shorter, because it stops. If your two traces are
     the same length, your branch isn't working — and this is the fastest way
     anyone will ever find that out. -->

From `python app.py ask '90s track jacket in size M' --trace`. This is try 1
of criterion 1 in `results/run_2026-10-13_1920_before.md`, cache off. Step 2 is the MCP call.

**Happy path**

```
[1] parse_query
      in:  90s track jacket in size M
      out: {'description': '90s track jacket in', 'size': 'M', 'max_price': None}
[2] search_listings (via MCP)
      in:  {'description': '90s track jacket in', 'size': 'M', 'max_price': None}
      out: 5 items: 90s Track Jacket — Navy/White Stripe, 90s Leather Bomber — Black, Bucket Hat — Reversible, Brown Plaid … +2 more
      →    5 match(es)
[3] select_item
      out: 90s Track Jacket — Navy/White Stripe ($45.0, poshmark)
      →    id lst_004, first of the results
[4] suggest_outfit
      in:  90s Track Jacket — Navy/White Stripe ($45.0, poshmark)
      out: Outfit 1: Pair the 90s Track Jacket with the white ribbed tank top, baggy straight-leg jeans, and chunky white…
      →    10 wardrobe item(s)
[5] create_fit_card
      in:  90s Track Jacket — Navy/White Stripe ($45.0, poshmark)
      out: Scored this vintage Champion track jacket on Poshmark for just $45 and it’s basically my new uniform. Whether …
```

Why each step was chosen. The session had no `parsed` yet, so the loop parsed
first. With `parsed` set and no `selected_item`, it searched over MCP. The
search returned 5 (not `[]`), so the branch took `results[0]`. With an item and
no outfit, it called `suggest_outfit`. With an outfit and no card, it called
`create_fit_card`. Then `fit_card` was set and the `while` condition ended the
loop.

**Empty search**

```
[1] parse_query
      in:  designer ballgown size XXS under $5
      out: {'description': 'designer ballgown', 'size': 'XXS', 'max_price': 5.0}
[2] search_listings (via MCP)
      in:  {'description': 'designer ballgown', 'size': 'XXS', 'max_price': 5.0}
      out: [] (empty)
      →    0 match(es)
[3] branch
      →    search returned []: stopping before suggest_outfit
```

Three steps instead of five. The branch set `session["error"]`, and the
`while` condition ended the loop before either model tool ran (0 model calls).

**On the MCP move:** `search_listings` now lives behind an MCP server
(`mcp_server.py`, registered with `@mcp.tool()`, typed inputs `description: str`,
`size: str | None`, `max_price: float | None`, matching the Tool Inventory).
In `agent.py` I replaced `from tools import search_listings` with a small
`agent.py::search_listings` that calls `mcp_client.call_tool("search_listings",
{...})`. Every search in the agent goes through it, including the
re-searches `_empty_search_message` runs to work out which filter to drop.
`suggest_outfit` and `create_fit_card` are still direct calls.
`python mcp_client.py` lists the tool with its description and its three inputs
(`description: string`, `size: string (optional)`, `max_price: number (optional)`).

Nothing behaved differently afterwards. I compared the direct and MCP calls on
three queries (`vintage graphic tee` ≤ $30, `platform sneakers` size 8, the
impossible ballgown). Both returned identical lists (`==` was True), prices
came back as `float`, and the empty case came back as `[]`, not None. The
`vintage graphic tee under $30` run picked the same item (Y2K Baby Tee, $18,
depop) as in unit 3. The only thing that changed was speed. Each MCP call starts
the server as a new process, so a search takes roughly half a second instead of
being instant. An empty search with a size and a price makes up to three MCP calls.

If the server can't be reached, `run_agent` catches `MCPError` and says
"The listings search couldn't be reached… Check that `python mcp_server.py`
starts without an error". It doesn't silently fall back to the direct call,
because a fallback would hide whether the MCP path was actually being used.

### Failure modes, triggered on purpose

**1. Empty search.** `python app.py ask 'designer ballgown size XXS under $5'`

```
  No listings matched 'designer ballgown' in size XXS under $5. To find something, try different words for the item — nothing in the listings matches those words at any size or price. Broader terms like 'tee', 'jacket', 'jeans' or 'sneakers' cover more of the data.

0 model calls this session
```

This handler already existed from unit 3 (`agent.py::_empty_search_message`).
When dropping a filter would help, it says so with numbers instead, e.g.
`'graphic tee size M under $10'` → "raise your max price — 2 match without the
$10 limit, the cheapest at $15".

**2. Empty wardrobe.** `python app.py ask 'denim jacket under $50' --empty-wardrobe`

```
(running with an empty wardrobe)
  Found:    Denim Jacket — Light Wash, Cropped — $42.0 on poshmark

  Outfit:   **Outfit 1 (Denim on Denim):** Pair with black straight-leg jeans, a plain white t-shirt, and white sneakers for a classic, high-contrast look.

**Outfit 2 (Off-Duty Casual):** Throw it over a grey cotton hoodie and black leggings, finished with comfortable retro-runner sneakers.

  Fit card: Scored this vintage Wrangler light-wash cropped denim jacket on Poshmark for just $42. It’s got that perfectly broken-in feel and looks so good thrown over a grey hoodie or paired with black straight-leg denim. A timeless streetwear staple that I’ll be wearing on repeat. 👖✨
```

No crash and no empty string. `tools.py::suggest_outfit` already switched to a
"common basics" prompt when `wardrobe["items"]` was empty, so no new handler was
needed. It also ran 5 of 5 times as the diagnostic scenario in the run log.

**3. Model unavailable.** I changed the last character of the key for one command
(`GEMINI_API_KEY=<key with last char changed> AI201_CACHE=0 python app.py ask
'corduroy jacket under $60'`, a query I hadn't run before, with the cache off).

Before the handler (unit 3 code), the run ended with one line and the search
result was lost:

```
ModelUnavailable: The model rejected your API key. Check GEMINI_API_KEY in your .env file, or create a fresh key at aistudio.google.com.
```

It wasn't a stack trace, because `app.py::main` catches everything. But it
showed a Python class name and threw away the search result, which had worked.
I added a `ModelUnavailable` handler in `agent.py::run_agent`. Now it returns
in about 1 second, with no hang:

```
[1] parse_query
      in:  corduroy jacket under $60
      out: {'description': 'corduroy jacket', 'size': None, 'max_price': 60.0}
[2] search_listings (via MCP)
      in:  {'description': 'corduroy jacket', 'size': None, 'max_price': 60.0}
      out: 4 items: Corduroy Wide-Leg Pants — Rust, Denim Jacket — Light Wash, Cropped, 90s Track Jacket — Navy/White Stripe … +1 more
      →    4 match(es)
[3] select_item
      out: Corduroy Wide-Leg Pants — Rust ($32.0, depop)
      →    id lst_005, first of the results
[4] model unavailable
      →    stopping; search result kept

  The styling model couldn't be reached, so no outfit or fit card was written. The search still worked: the best match was Corduroy Wide-Leg Pants — Rust — $32 on depop. Check that GEMINI_API_KEY in .env is correct and that you're online, then run the same query again.
(What the service said: The model rejected your API key. Check GEMINI_API_KEY in your .env file, or create a fresh key at aistudio.google.com.)
```



---

## The Improvement

<!-- What you changed, why your diagnosis pointed at it, and the after-run in
     the same table format. One change, measured properly.

     `python run_eval.py --label after` -->

**What I changed:**

**Which failure it was meant to fix:**

### Run Log — After

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Did it help, and how do I know:**

<!-- If it made things worse, say that. Honestly reported, that earns full
     credit and is more interesting than one that worked. -->



---

## What's Still Broken

<!-- For each criterion still missed: what you'd do, and why you stopped where
     you did. "I ran out of time" is fine if it's true. Pretending nothing is
     left is not. -->



<!-- ═════════════════════════════════════════════════════════════════════

     SUBMISSION CHECKLIST — unit 3

       [ ] criteria.md has five numbered criteria, each with a target
       [ ] Each criterion has a reason underneath it
       [ ] All five unit 3 sections above have real content
       [ ] Tool Inventory: all three tools, inputs WITH TYPES, a specific
           return value, and the empty case
       [ ] Planning Loop names the branch rule and agent.py::run_agent
       [ ] Sample Run: one full query plus the three per-tool tests, as text
       [ ] At least four new commits
       [ ] Repository URL submitted — WRITE IT DOWN, you submit the same one
           next unit

     SUBMISSION CHECKLIST — unit 4

       [ ] mcp_server.py exists with one tool registered
           (or a written record of exactly where the rewire broke)
       [ ] Run Log — Before, five criteria, five tries each
       [ ] Real output pasted underneath, naming file and function
       [ ] A verdict on every criterion
       [ ] A diagnosis for every miss, naming a place AND a mechanism
       [ ] Loop Trace, with the MCP call visible in it
       [ ] All three failure modes triggered and handled
       [ ] One improvement, with Run Log — After in the same format
       [ ] What's Still Broken
       [ ] At least four new commits
       [ ] The SAME repository URL as last unit

     Do not delete and recreate this repository. Your commit history is what
     shows your criteria existed before your results did.
     ═════════════════════════════════════════════════════════════════════ -->

---

📖 **How to run this project: [RUNNING.md](RUNNING.md)**
