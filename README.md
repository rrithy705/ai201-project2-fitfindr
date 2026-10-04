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
$ python app.py ask '...'

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
$ python -c "from tools import suggest_outfit; ..."

```

```
$ python -c "from tools import create_fit_card; ..."

```

---

## How I Used AI

<!-- Two specific moments. What you asked, what came back, what you changed.

     "I used Claude to help me code" is not enough.

     "I gave Claude my search_listings spec. It returned None on no match
     instead of an empty list, so I changed it" is the level we want. -->

**Moment 1**

- *What I asked for:*
- *What came back:*
- *What I changed:*

**Moment 2**

- *What I asked for:*
- *What came back:*
- *What I changed:*

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

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Real output from one try**, pasted as text, naming the file and function
that produced it:

```

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
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |

**Diagnoses**



---

## Loop Trace

<!-- One full run, printed step by step, with the MCP call visible in it.

     `python app.py ask '...' --trace` once you've added the trace.step()
     calls in Milestone 2.

     Worth pasting BOTH the happy path and the empty-search path. The empty
     one should be visibly shorter, because it stops. If your two traces are
     the same length, your branch isn't working — and this is the fastest way
     anyone will ever find that out. -->

**Happy path**

```

```

**Empty search**

```

```

**On the MCP move:** <!-- what changed in your code, and whether anything
behaved differently afterwards. If the rewire didn't work, say exactly where it
broke — the error text and the last thing that worked. That earns the point in
full. -->



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
